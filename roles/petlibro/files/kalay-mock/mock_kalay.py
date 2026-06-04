#!/usr/bin/env python3
"""
Mock Kalay master server + TCP-80 video-relay endpoint. Pretends to be the
TUTK cloud so feeders can register without internet, and catbro (or any
client speaking the Kalay master-server protocol) can ask "where is UID X?"
and get the feeder's LAN endpoint back. The optional TCP-80 listener also
catches the Kalay-over-TCP fallback path used for cloud-relayed video.

Protocol references:
  - Charlie cipher: bobobo1618/go2rtc/pkg/tutk/crypto.go (ported to decrypt.py)
  - Client opcodes: bobobo1618/go2rtc/pkg/tutk/session0.go (ConnectByUID,
    connectRemote)
  - Device opcodes: petlibro-working.pcap analysis (LEARNINGS.md)
  - TCP-80 transport: wave-test capture, see LEARNINGS.md "TCP-80 MOCK BUILT"

Usage (development):
  python3 mock_kalay.py --bind 0.0.0.0 --port 10001 --port 10240 \\
                       --tcp-port 10080 --av-dump-dir ./av-dump -vv

Production deploy:
  UDM iptables (idempotent; see /mnt/data/on_boot.d/10-petlibro-nat.sh):

    # UDP master-server path
    for IP in 35.175.133.25 3.236.223.147 100.28.210.188; do
      iptables -t nat -A PREROUTING -p udp -d $IP --dport 10001 \\
               -j DNAT --to <mock_ip>:10001
    done
    for IP in 45.79.40.130 34.193.155.98; do
      iptables -t nat -A PREROUTING -p udp -d $IP --dport 10240 \\
               -j DNAT --to <mock_ip>:10240
    done

    # TCP-80 video-relay path (also needs MASQUERADE for return)
    for IP in 35.175.133.25 3.236.223.147 100.28.210.188 \\
              34.193.155.98 45.79.40.130; do
      iptables -t nat -A PREROUTING -p tcp -d $IP --dport 80 \\
               -j DNAT --to <mock_ip>:10080
    done
    iptables -t nat -A POSTROUTING -d <mock_ip> -p tcp --dport 10080 \\
             -j MASQUERADE

File layout (for quick navigation):
   L60-130    constants — MAGIC, version bytes, opcode tuples, well-known IPs
   L135-185   Registry / FeederRecord — thread-safe UID → endpoint map
   L190-240   protocol primitives — build_packet, encrypt, sockaddr_in, extract_uid
   L240-380   UDP response builders — make_stun_response, make_register_ack,
              make_punch_to2, make_edge_list, make_lookup_response, …
   L380-490   TCP-80 transport — make_tcp_reg_ack, make_tcp_lookup_resp,
              read_kalay_tcp_packet
   L490-520   AVStream — per-feeder AV chunk sink (queue + file dump)
   L520-660   MockKalayTCP — TCP/80 server, dispatches on opcode
   L660-940   MockKalay — UDP servers (10001/10240), legacy handler set
   L940-      main() / CLI entrypoint
"""
from __future__ import annotations
import argparse
import logging
import queue
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from decrypt import reverse_trans_code_blob, reverse_trans_code_partial, trans_code_blob

log = logging.getLogger("mock_kalay")

# Magic constants from observation
MAGIC = b"\x04\x02"
VERSION_DEVICE = 0x1b  # what our feeders use
VERSION_SERVER = 0x1d  # what we send back

# Plaintext bootstrap from the feeder's first packet to a new server
BOOTSTRAP_MAGIC = b"\xcc\xaa\xab\xab"

# Dedicated source port for outbound PUNCH_TO2 packets to feeders.
# Distinct from the listening ports (10001, 10240) so that the kernel's
# conntrack state doesn't merge outbound PUNCH_TO2 with the long-lived
# inbound keepalive flows on :10001. The corresponding iptables SNAT
# rule must filter on --sport=PUNCH_TO2_OUT_PORT.
PUNCH_TO2_OUT_PORT = 10099

# When the GET_RIP request comes from a Docker bridge (172.16.0.0/12) or
# other private container subnet that feeders can't reach directly, the
# mock must substitute the host's LAN IP for the client_wan_ip encoded
# in PUNCH_TO2. Otherwise the feeder's proactive KNOCK goes to an
# unrouteable private address.
HOST_LAN_IP = "192.168.1.6"


def _client_ip_for_punch(src_ip: str) -> str:
    """Return the IP feeders will actually see as the client's source.

    Docker containers MASQUERADE outbound packets through the host's
    primary interface, so the feeder receives them with src=host IP.
    PUNCH_TO2 needs to encode that host IP, not the container's private
    bridge IP.
    """
    if src_ip.startswith("172.") or src_ip.startswith("10.") or src_ip == "127.0.0.1":
        return HOST_LAN_IP
    if src_ip.startswith("192.168.") and not src_ip.startswith("192.168.1."):
        # Other internal subnets we host (e.g. libvirt 192.168.122.x)
        return HOST_LAN_IP
    return src_ip

# Opcodes we recognize (offset 8-10, with offset 11 always 0)
# Device → cloud
OP_DEV_STUN_REQ     = (0x07, 0x10, 0x18)
OP_DEV_REG_FULL     = (0x20, 0x01, 0x14)
OP_DEV_BULK_KEEP    = (0x22, 0x01, 0x14)
OP_DEV_QUERY        = (0x0c, 0x03, 0x14)
OP_DEV_SMALL_KEEP   = (0x03, 0x80, 0x3f)

# Client (catbro) → cloud — bobobo1618's connectRemote flow
OP_CLIENT_GET_RIP   = (0x03, 0x02, 0x34)
OP_CLIENT_REMOTE_REQ= (0x01, 0x04, 0x33)
OP_CLIENT_REMOTE_ACK= (0x02, 0x04, 0x33)
OP_CLIENT_REMOTE_OK = (0x04, 0x04, 0x33)
OP_CLIENT_BCAST     = (0x01, 0x06, 0x21)   # also used in stageDirect

# Cloud responses we generate
OP_SRV_STUN_RESP        = (0x04, 0x80, 0x4f)
OP_SRV_REG_ACK          = (0x0b, 0x01, 0x41)
OP_SRV_SESSION_NEXT_ACK = (0x0d, 0x01, 0x41)  # guessed by req+1 / 14→41 pattern
OP_SRV_REG_ACK_VARIANT  = (0x21, 0x01, 0x41)
OP_SRV_KEEPALIVE_ACK    = (0x23, 0x01, 0x41)
OP_SRV_BIG_PUSH         = (0x01, 0x03, 0x43)  # also the lookup-response opcode
OP_SRV_LOOKUP_RESP_VAR  = (0x03, 0x03, 0x43)
OP_SRV_EDGE_LIST        = (0x08, 0x10, 0x83)

# New device opcode we discovered in live deployment (post-REG_FULL session step)
OP_DEV_SESSION_NEXT     = (0x0c, 0x01, 0x14)

# AV session opcodes — used on TCP/80 transport
OP_DEV_AV_DATA          = (0x02, 0x05, 0x14)  # feeder → cloud: AV chunk/control
OP_DEV_AV_DATA_VARIANT  = (0x22, 0x05, 0x14)  # feeder → cloud: AV variant
OP_SRV_AV_CONTROL       = (0x01, 0x05, 0x41)  # cloud → feeder: AV session control

# Default 8-byte session id we hand out in TCP REG_ACK. Captured from a
# live cloud session. Charlie/Kalay treats this as opaque — the feeder
# echoes it back in subsequent AV-session frames.
TCP_DEFAULT_SID8 = bytes.fromhex("8b79ed745d6389c3")


@dataclass
class FeederRecord:
    """What we know about a feeder that has registered with us."""
    uid: str
    lan_ip: str
    lan_port: int
    external_ip: str          # what the feeder would see as its NAT'd public addr
    external_port: int
    last_seen: float
    firmware: Optional[str] = None
    session_token: Optional[bytes] = None  # 8-byte trailer extracted from F2C_REG_FULL


class Registry:
    """Thread-safe map of UID → FeederRecord."""
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_uid: dict[str, FeederRecord] = {}

    def upsert(self, uid: str, src_ip: str, src_port: int, **kwargs) -> FeederRecord:
        with self._lock:
            rec = self._by_uid.get(uid)
            now = time.time()
            if rec is None:
                rec = FeederRecord(
                    uid=uid,
                    lan_ip=src_ip, lan_port=src_port,
                    external_ip=src_ip, external_port=src_port,
                    last_seen=now,
                )
                self._by_uid[uid] = rec
                log.info("registered new feeder %s at %s:%d", uid, src_ip, src_port)
            else:
                if (rec.lan_ip, rec.lan_port) != (src_ip, src_port):
                    log.info("feeder %s moved %s:%d → %s:%d",
                             uid, rec.lan_ip, rec.lan_port, src_ip, src_port)
                    rec.lan_ip = src_ip
                    rec.lan_port = src_port
                    rec.external_ip = src_ip
                    rec.external_port = src_port
                rec.last_seen = now
            for k, v in kwargs.items():
                if v is not None:
                    setattr(rec, k, v)
            return rec

    def get(self, uid: str) -> Optional[FeederRecord]:
        with self._lock:
            return self._by_uid.get(uid)

    def snapshot(self) -> dict[str, FeederRecord]:
        with self._lock:
            return dict(self._by_uid)


# ---------- helpers for building packets ----------

def sockaddr_in(ip: str, port: int) -> bytes:
    """Encode an IPv4 endpoint as the 8-byte sockaddr_in we see in TUTK packets:
       [family u16 LE = 2][port u16 BE][ipv4 u32 BE]"""
    parts = ip.split(".")
    assert len(parts) == 4, f"bad ipv4: {ip}"
    family = struct.pack("<H", 2)
    port_be = struct.pack(">H", port)
    ip_be = bytes(int(p) for p in parts)
    return family + port_be + ip_be


def build_packet(opcode: tuple[int, int, int], payload: bytes,
                 version: int = VERSION_SERVER, subtype: int = 0x00,
                 field10: int = 0x41, field12: int = 0) -> bytes:
    """Build a 16-byte header + payload, return PLAINTEXT (caller must encrypt)."""
    hdr = bytearray(16)
    hdr[0:2] = MAGIC
    hdr[2] = version
    hdr[3] = subtype
    struct.pack_into("<I", hdr, 4, len(payload))
    hdr[8] = opcode[0]
    hdr[9] = opcode[1]
    hdr[10] = opcode[2]
    hdr[11] = 0
    struct.pack_into("<I", hdr, 12, field12)
    return bytes(hdr) + payload


def encrypt(pt: bytes) -> bytes:
    return trans_code_blob(pt)


def decrypt(ct: bytes) -> bytes:
    return reverse_trans_code_blob(ct)


def extract_uid(plaintext_body: bytes) -> Optional[str]:
    """UID is the first 20 ASCII chars in body (or somewhere near the start).
    Conservative scan."""
    for i in range(min(len(plaintext_body) - 19, 40)):
        chunk = plaintext_body[i:i + 20]
        if all(32 <= c < 127 for c in chunk):
            s = chunk.decode('ascii', errors='ignore')
            if s.endswith("111A") and s[:-4].isalnum():
                return s
    return None


# ---------- response builders ----------

def make_stun_response(external_ip: str, external_port: int) -> bytes:
    """Body of 24 bytes: sockaddr (8) + zeros (8) + trailer (8). Total wire 40."""
    body = sockaddr_in(external_ip, external_port) + b"\x00" * 8 + b"\x00" * 8
    return build_packet(OP_SRV_STUN_RESP, body, field10=0x4f, subtype=0x00)


def make_register_ack(uid: str) -> bytes:
    """48-byte C2F_REG_ACK (op=0x0b 01 41). Body matches the EXACT bytes
    observed in petlibro-working.pcap:
        UID(20) + 10 18 f0 80 + 4a 2d 7c 87 00 00 7c 87
    The trailer bytes look like a session-derived token. Hardcoding the
    observed value as a starting point — if the feeder rejects, this is
    the first thing to refine."""
    body = uid.encode().ljust(20, b"\x00")
    body += b"\x10\x18\xf0\x80"
    body += b"\x4a\x2d\x7c\x87\x00\x00\x7c\x87"
    return build_packet(OP_SRV_REG_ACK, body, field10=0x41, subtype=0x00)


def make_register_ack_variant(uid: str) -> bytes:
    """44-byte C2F_REG_ACK_VARIANT (op=0x21 01 41). Body from observed pcap:
        UID(20) + 03 00 00 00 + 78 17 16 6a"""
    body = uid.encode().ljust(20, b"\x00")
    body += b"\x03\x00\x00\x00"
    body += b"\x78\x17\x16\x6a"
    return build_packet(OP_SRV_REG_ACK_VARIANT, body, field10=0x41, subtype=0x00)


def make_session_next_ack(uid: str) -> bytes:
    """Response to OP_DEV_SESSION_NEXT (0c 01 14) — opcode guessed.
    Same body shape as REG_ACK to start."""
    body = uid.encode().ljust(20, b"\x00")
    body += b"\x10\x18\xf0\x80"
    body += b"\x4a\x2d\x7c\x87\x00\x00\x7c\x87"
    return build_packet(OP_SRV_SESSION_NEXT_ACK, body, field10=0x41, subtype=0x00)


def make_punch_to2(uid: str, client_random_id: int,
                   client_wan_ip: str, client_wan_port: int,
                   client_lan_ip: str = "0.0.0.0", client_lan_port: int = 0,
                   client_nat: int = 2, device_nat: int = 2,
                   session_token: Optional[bytes] = None) -> bytes:
    """Cloud→device MSG_P2P_PUNCH_TO2 (IOTC layer, opcode 0x01 0x03 0x43).

    Body layout reverse-engineered from a REAL cloud PUNCH_TO2 captured on
    2026-05-28 (cellular-punch.pcap). Real body is 292 bytes (NOT 132 as
    the dispatcher upper-bound check suggested). Earlier shorter bodies
    were silently rejected by the feeder.

    Body layout (offsets into the 292-byte body):
      0x00..0x14 (20)   UID
      0x14..0x1c (8)    Client WAN sockaddr_in
      0x1c..0x24 (8)    zeros (padding for WAN)
      0x24..0x2c (8)    "Client LAN" sockaddr — real had family=0x0000 but
                        valid port+IP; we use family=2 since LAN really is
                        AF_INET and the handler appears tolerant.
      0x2c..0x34 (8)    zeros
      0x34..0x40 (12)   Mystery candidate slot #1 — observed
                        `00 00 PP PP c0 00 00 06 00 00 00 00`. Looks like
                        sockaddr with family=0 and IP `192.0.0.6` (IETF
                        reserved). Likely a P2P-candidate filler. Repeated
                        3x at offsets 0x34, 0x44, 0x54 (16B apart but only
                        12B of structure used).
      ... (more zeros and slots)
      0x64..0x6c (8)    Session token (sid8) — full 8 bytes, not just rid.
                        First 4 bytes act as ClientRandomID (matched by
                        feeder against KNOCK2's random id).
      0x6c..0x70 (4)    ClientNAT type (LE u32) — real cloud sent 2
                        (restricted) not 1 (full cone) as previously
                        hardcoded.
      0x70..0x74 (4)    DeviceNAT type (LE u32) — also 2.
      0x74..0x120 (172) zeros — handler-tolerant pad area.
      0x120..0x124 (4)  Trailer magic `22 1a 22 1a` — appears as constant
                        across all observed real PUNCH_TO2 packets.

    Subtype byte 3 = 0x02 — matches the framing used by other IOTC-layer
    messages.
    """
    body = bytearray(0x124)  # 292 bytes — matches real cloud body length
    body[0x00:0x14] = uid.encode().ljust(20, b"\x00")
    # Client WAN sockaddr: AF_INET (family=2), port BE, IP BE
    body[0x14:0x1c] = sockaddr_in(client_wan_ip, client_wan_port)
    # Client LAN sockaddr at [0x24]: real cloud uses family=0 (NOT AF_INET)
    # with valid port+IP. Treating as a P2P-candidate marker. Use WAN
    # endpoint here when LAN isn't separately known.
    lan_ip = client_lan_ip if client_lan_ip != "0.0.0.0" else client_wan_ip
    lan_port = client_lan_port if client_lan_port else client_wan_port
    struct.pack_into(">H", body, 0x26, lan_port)  # port BE at [0x26:0x28]
    body[0x28:0x2c] = bytes(int(p) for p in lan_ip.split("."))
    # 3 mystery P2P-candidate slots at [0x34], [0x44], [0x54], each:
    #   family=0x0000  port=client_wan_port BE  IP=c0 00 00 06  + 4B zeros
    # The IP 192.0.0.6 is IETF-reserved and shows up identically across
    # captured PUNCH_TO2s — looks like a literal protocol filler that the
    # feeder's validator may require.
    for slot_off in (0x34, 0x44, 0x54):
        struct.pack_into(">H", body, slot_off + 2, client_wan_port)
        body[slot_off + 4:slot_off + 8] = b"\xc0\x00\x00\x06"
    # Session token: 8 bytes at 0x64. First 4 bytes effectively act as
    # ClientRandomID (matched by feeder against KNOCK2's random id).
    if session_token is not None:
        assert len(session_token) == 8
        body[0x64:0x6c] = session_token
    else:
        struct.pack_into("<I", body, 0x64, client_random_id)
    # NAT type fields
    struct.pack_into("<I", body, 0x6c, client_nat)
    struct.pack_into("<I", body, 0x70, device_nat)
    # Trailer magic at end of body
    body[0x120:0x124] = b"\x22\x1a\x22\x1a"
    return build_packet(OP_SRV_BIG_PUSH, bytes(body), field10=0x43, subtype=0x02)


def make_edge_list(uid: str, mock_ip: str, mock_port: int,
                   feeder_ip: Optional[str] = None,
                   feeder_port: Optional[int] = None) -> bytes:
    """C2F_EDGE_LIST (op=0x08 10 83) — 142-byte packet (126B body).

    Master server's reply to a feeder's STUN_REQ (opcode 07,10,18) on port
    10240. Body layout reverse-engineered from a real-cloud capture:

        body[0x00:0x14]  UID
        body[0x14:0x24]  16B zeros
        body[0x24:0x2c]  feeder's external sockaddr (STUN echo) — where
                         the cloud saw the feeder coming from. On our LAN,
                         this is just the feeder's source IP+port.
        body[0x2c:0x34]  8B zeros
        body[0x34:0x3c]  TLV header `05 00 03 00 02 00 30 00`
        body[0x3c:0x6c]  3 × (sockaddr 8B + zeros 8B) — the actual relay
                         endpoints the feeder should connect to next (port
                         10001). Real cloud lists 3 different IPs; we
                         repeat ours since we're the only "relay".
        body[0x6c:0x74]  end-of-list `03 00 04 00 30 00 00 00`
        body[0x74:0x7e]  10B trailer `01 00 06 00 02 a3 01 00 5a 00`
    """
    # When feeder_ip/port aren't given, fall back to mock_ip/port — older
    # callers used this for both slots, which worked weakly because the
    # feeder mostly cared about the relay list, not the STUN echo.
    if feeder_ip is None:
        feeder_ip = mock_ip
    if feeder_port is None:
        feeder_port = mock_port
    body = uid.encode().ljust(20, b"\x00")
    body += b"\x00" * 16
    body += sockaddr_in(feeder_ip, feeder_port)  # body[0x24:0x2c] feeder STUN echo
    body += b"\x00" * 8                          # body[0x2c:0x34] zeros
    body += b"\x05\x00\x03\x00\x02\x00\x30\x00"  # body[0x34:0x3c] TLV header
    # 3 entries pointing at our mock (replacing the 3 real Kalay AWS IPs)
    for _ in range(3):
        body += sockaddr_in(mock_ip, mock_port)
        body += b"\x00" * 8
    body += b"\x03\x00\x04\x00\x30\x00\x00\x00"  # end-of-list marker
    body += b"\x01\x00\x06\x00\x02\xa3\x01\x00\x5a\x00"  # trailer
    return build_packet(OP_SRV_EDGE_LIST, body, field10=0x83, subtype=0x00)


def make_keepalive_ack(uid: str, external_ip: str, external_port: int) -> bytes:
    """C2F_KEEPALIVE_ACK (op=0x23): UID(20) + sockaddr(8) + 4 zeros + trailer(8)."""
    body = uid.encode().ljust(20, b"\x00")
    body += sockaddr_in(external_ip, external_port)
    body += b"\x00\x00\x00\x00"
    body += b"\x09\x09\x13\x13\x04\x1a\x1b\x63"  # trailer copied from observed packet
    return build_packet(OP_SRV_KEEPALIVE_ACK, body, field10=0x41, subtype=0x00)


def make_lookup_response(uid: str, target_ip: str, target_port: int,
                         sid8: bytes = b"\x10\x18\xf0\x80\x4a\x2d\x7c\x87") -> bytes:
    """Answer catbro's OP_CLIENT_GET_RIP (`\\x03\\x02\\x34`) with the device
    endpoint.

    bobobo1618's `connectRemote()` reads:
        port  = BigEndian uint16 at res[38..40]
        ip    = res[40..44]
        sid8  = res[72..80]    ← used by subsequent KNOCK2

    The 16-byte header is res[0..16], so res[38..40] is BODY offset 22..24,
    res[40..44] is BODY offset 24..28, and res[72..80] is BODY offset 56..64.

    sid8 should be the same 8 bytes the client sent in GET_RIP — that way
    the client uses the same session ID end-to-end and we can predict the
    ClientRandomID (first 4 bytes of sid8) to pre-populate the feeder's
    gPreSessionInfo via PUNCH_TO2.
    """
    assert len(sid8) == 8
    body = uid.encode().ljust(20, b"\x00")
    body += sockaddr_in(target_ip, target_port)  # body[20..28] — read by client
    body += b"\x00" * 8                          # body[28..36]
    body += sockaddr_in(target_ip, target_port)  # body[36..44] — alternate slot
    body += b"\x00" * 8                          # body[44..52]
    body += b"\x00" * 4                          # body[52..56] — pad
    body += sid8                                  # body[56..64] = res[72..80] ← sid8
    body += b"\x02\x03\x03\x04"                  # body[64..68] — version-ish
    body += b"\x04\x07\x04\x03"                  # body[68..72]
    body += b"\x1c\x00\x00\x00\x1b\x00\x00\x00"  # body[72..80] — counters
    body += b"\x63\x06\x13\x13\x04\x0c\x0c\x61"  # body[80..88] — trailer
    return build_packet(OP_SRV_BIG_PUSH, body, field10=0x43, subtype=0x00)


# ---------- TCP-80 transport (Kalay-over-TCP for AV) ----------
#
# Some Kalay deployments use TCP/80 instead of UDP for the video session
# (useful when networks block arbitrary UDP). Our feeders open an outbound
# TCP connection to one of the Kalay relay IPs (e.g. 35.175.133.25:80) and
# run the SAME Charlie-encrypted Kalay framing over the byte stream.
#
# Wire shape captured from a live cloud session:
#   feeder → cloud (initial):
#     hdr(16) op=(0c,01,14) ver=0x1b sub=0x02 body_len=32
#     body = UID(20) + b"\\x0c\\x01\\x14\\x00\\x00\\x00\\x00\\x00" + ...
#   cloud → feeder (handshake reply, 2 packets):
#     A) hdr op=(0b,01,41) ver=0x1d sub=0x00 body_len=32
#        body = UID(20) + sid8(8) + tail(4)
#     B) hdr op=(03,03,43) ver=0x1d sub=0x02 body_len=88
#        body = UID(20) + b"\\x2e\\x01\\x00\\x00" + sockaddr(8) + ...
#   subsequent AV session:
#     feeder → cloud op=(02,05,14) ver=0x1c sub=0x0a  — AV payload
#     cloud → feeder op=(01,05,41) ver=0x1c sub=0x0a  — AV control / msgid acks


def make_tcp_reg_ack(uid: str, sid8: bytes) -> bytes:
    """Cloud→feeder REG_ACK over TCP-80. Body is 32 bytes:
        UID(20) + sid8(8) + tail(4 — observed `00 00 89 c3`)
    The tail bytes appear to be sid8[6:8] echoed with a 2-byte zero prefix."""
    assert len(sid8) == 8
    body = uid.encode().ljust(20, b"\x00")
    body += sid8
    body += b"\x00\x00" + sid8[6:8]
    return build_packet(OP_SRV_REG_ACK, body,
                        version=VERSION_SERVER, subtype=0x00, field10=0x41)


def make_tcp_lookup_resp(uid: str, sid8: bytes,
                         wan_ip: str, wan_port: int,
                         alt_port: Optional[int] = None) -> bytes:
    """Cloud→feeder LOOKUP_RESP_VAR (03,03,43) over TCP-80. Body is 88 bytes,
    laid out from a live capture as:
        0x00..0x14 (20) UID
        0x14..0x18 (4)  tag `2e 01 00 00`
        0x18..0x20 (8)  primary sockaddr (feeder's apparent WAN endpoint)
        0x20..0x28 (8)  zero padding
        0x28..0x30 (8)  alternate sockaddr (same IP, different port slot)
        0x30..0x38 (8)  zero padding
        0x38..0x40 (8)  sid8 (matches the one we sent in REG_ACK)
        0x40..0x48 (8)  version-ish bytes (`02 03 03 04 04 07 04 03`)
        0x48..0x50 (8)  counters (`1c 00 00 00 1b 00 00 00`)
        0x50..0x58 (8)  trailer (`50 39 19 34 30 41 a7 06` in capture)
    """
    assert len(sid8) == 8
    alt_port = alt_port if alt_port is not None else wan_port
    body = bytearray(88)
    body[0x00:0x14] = uid.encode().ljust(20, b"\x00")
    body[0x14:0x18] = b"\x2e\x01\x00\x00"
    body[0x18:0x20] = sockaddr_in(wan_ip, wan_port)
    # body[0x20:0x28] stays zero
    body[0x28:0x30] = sockaddr_in(wan_ip, alt_port)
    # body[0x30:0x38] stays zero
    body[0x38:0x40] = sid8
    body[0x40:0x48] = b"\x02\x03\x03\x04\x04\x07\x04\x03"
    body[0x48:0x50] = b"\x1c\x00\x00\x00\x1b\x00\x00\x00"
    body[0x50:0x58] = b"\x50\x39\x19\x34\x30\x41\xa7\x06"
    return build_packet(OP_SRV_LOOKUP_RESP_VAR, bytes(body),
                        version=VERSION_SERVER, subtype=0x02, field10=0x43)


def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    """Read exactly n bytes. Returns None on EOF before n bytes arrive."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def read_kalay_tcp_packet(sock: socket.socket) -> Optional[bytes]:
    """Read one full Charlie-encrypted Kalay packet from a TCP socket and
    return the decrypted plaintext. Returns None on EOF or unrecoverable
    framing error.

    The Charlie cipher operates on independent 16-byte blocks, so we can
    safely decrypt the 16-byte header first, read body length from
    hdr[4:8] LE, then read & decrypt the body separately."""
    hdr_enc = _recv_exact(sock, 16)
    if hdr_enc is None:
        return None
    hdr_pt = reverse_trans_code_partial(hdr_enc)
    if hdr_pt[:2] != MAGIC:
        log.warning("TCP: bad magic after decrypt: %s (raw %s)",
                    hdr_pt[:4].hex(), hdr_enc[:4].hex())
        return None
    body_len = struct.unpack_from("<I", hdr_pt, 4)[0]
    if body_len > 1 << 20:  # sanity: >1 MiB body is almost certainly desync
        log.warning("TCP: implausible body_len=%d — aborting stream", body_len)
        return None
    if body_len == 0:
        return hdr_pt
    body_enc = _recv_exact(sock, body_len)
    if body_enc is None:
        return None
    body_pt = reverse_trans_code_blob(body_enc)
    return hdr_pt + body_pt


class AVStream:
    """Per-feeder AV chunk sink. Writes raw AV bytes (with their Kalay
    packet trailer/metadata still in place) to a dump file and into a
    queue that downstream consumers (e.g. go2rtc producer) can drain."""

    def __init__(self, dump_dir: Optional[Path] = None,
                 max_queue: int = 10_000) -> None:
        self.dump_dir = dump_dir
        if dump_dir:
            dump_dir.mkdir(parents=True, exist_ok=True)
        self.q: "queue.Queue[tuple[str, tuple[int,int,int], bytes]]" = queue.Queue(
            maxsize=max_queue)
        self._files: dict[str, "Path"] = {}
        self._lock = threading.Lock()

    def put(self, uid: str, opcode: tuple[int, int, int], body: bytes) -> None:
        try:
            self.q.put_nowait((uid, opcode, body))
        except queue.Full:
            log.warning("AVStream queue full — dropping chunk for %s", uid)
        if self.dump_dir:
            with self._lock:
                path = self._files.get(uid)
                if path is None:
                    path = self.dump_dir / f"{uid or 'unknown'}.bin"
                    self._files[uid] = path
            try:
                with open(path, "ab") as f:
                    f.write(body)
            except OSError as e:
                log.warning("AV dump write failed for %s: %s", uid, e)


class MockKalayTCP:
    """TCP-80 server speaking Charlie-encrypted Kalay framing.

    One connection per feeder. Per connection:
      1. Read packets until we see SESSION_NEXT, extract UID.
      2. Send REG_ACK (with our sid8) + LOOKUP_RESP_VAR.
      3. From then on: log every opcode, push AV-data bodies into the
         per-feeder AV stream sink. Unknown control opcodes are logged
         but otherwise ignored — we'll learn what acks are required
         empirically by watching feeder behavior.
    """

    def __init__(self, bind_addr: str, port: int,
                 av_stream: AVStream,
                 registry: Optional[Registry] = None) -> None:
        self.bind_addr = bind_addr
        self.port = port
        self.av_stream = av_stream
        self.registry = registry or Registry()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def serve_forever(self) -> None:
        self.sock.bind((self.bind_addr, self.port))
        self.sock.listen(16)
        log.info("listening on %s:%d (TCP)", self.bind_addr, self.port)
        while True:
            try:
                conn, addr = self.sock.accept()
            except KeyboardInterrupt:
                log.info("TCP server shutting down")
                return
            except Exception as e:
                log.exception("TCP accept failed: %s", e)
                continue
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            log.info("[TCP %s:%d] accept", *addr)
            t = threading.Thread(target=self._serve_conn,
                                 args=(conn, addr), daemon=True)
            t.start()

    def _serve_conn(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        src_ip, src_port = addr
        uid: Optional[str] = None
        sid8 = TCP_DEFAULT_SID8
        n_av = 0
        try:
            while True:
                pt = read_kalay_tcp_packet(conn)
                if pt is None:
                    log.info("[TCP %s:%d] EOF (uid=%s, av_chunks=%d)",
                             src_ip, src_port, uid, n_av)
                    return
                version = pt[2]
                subtype = pt[3]
                opcode = (pt[8], pt[9], pt[10])
                body = pt[16:]

                pkt_uid = extract_uid(body)
                if pkt_uid and not uid:
                    uid = pkt_uid
                    log.info("[TCP %s:%d] identified uid=%s",
                             src_ip, src_port, uid)
                    self.registry.upsert(uid, src_ip, src_port)

                log.debug(
                    "[TCP %s:%d] op=(%02x,%02x,%02x) ver=0x%02x sub=0x%02x"
                    " body=%d uid=%s",
                    src_ip, src_port, *opcode, version, subtype, len(body),
                    pkt_uid or uid)

                if opcode == OP_DEV_SESSION_NEXT:
                    if not uid:
                        log.warning("[TCP %s:%d] SESSION_NEXT without UID —"
                                    " can't reply", src_ip, src_port)
                        continue
                    log.info("[TCP %s:%d] SESSION_NEXT uid=%s — sending"
                             " REG_ACK + LOOKUP_RESP_VAR", src_ip, src_port,
                             uid)
                    conn.sendall(encrypt(make_tcp_reg_ack(uid, sid8)))
                    conn.sendall(encrypt(make_tcp_lookup_resp(
                        uid, sid8, src_ip, src_port)))

                elif opcode == OP_DEV_STUN_REQ:
                    # Client-side STUN_REQ over TCP/80: phone asks the master
                    # "where is UID X?" Body: UID(20) + AuthKey(16) + tag(2).
                    # Real cloud's response for this on TCP isn't captured, so
                    # we try the same packets we'd send for SESSION_NEXT:
                    # REG_ACK (binding sid8 to the session) followed by
                    # LOOKUP_RESP_VAR pointing at ourselves (so the phone
                    # opens its next TCP connection back to us, since the
                    # UDM DNAT covers the relay IPs we'd advertise).
                    log.info("[TCP %s:%d] STUN_REQ uid=%s — sending"
                             " REG_ACK + LOOKUP_RESP_VAR", src_ip, src_port,
                             uid)
                    if uid:
                        conn.sendall(encrypt(make_tcp_reg_ack(uid, sid8)))
                        conn.sendall(encrypt(make_tcp_lookup_resp(
                            uid, sid8, src_ip, src_port)))

                elif opcode == (0x14, 0x02, 0x24):
                    # Video-relay session init seen in wave-test capture
                    # (phone → 35.175.133.25:80). Body shape unknown yet —
                    # log and dump so we can inspect, then try REG_ACK +
                    # LOOKUP_RESP_VAR as a generic ack to keep the session
                    # alive long enough to see follow-up packets.
                    log.info("[TCP %s:%d] OP=(14,02,24) video-relay init"
                             " uid=%s body=%d — replying REG_ACK + LOOKUP",
                             src_ip, src_port, uid, len(body))
                    self.av_stream.put(uid or "unknown_ctl", opcode, body)
                    if uid:
                        conn.sendall(encrypt(make_tcp_reg_ack(uid, sid8)))
                        conn.sendall(encrypt(make_tcp_lookup_resp(
                            uid, sid8, src_ip, src_port)))

                elif opcode in (OP_DEV_AV_DATA, OP_DEV_AV_DATA_VARIANT):
                    n_av += 1
                    self.av_stream.put(uid or "unknown", opcode, body)
                    if n_av <= 5 or n_av % 100 == 0:
                        log.info("[TCP %s:%d] AV chunk #%d op=(%02x,%02x,%02x)"
                                 " sub=0x%02x body=%d", src_ip, src_port,
                                 n_av, *opcode, subtype, len(body))

                else:
                    log.info("[TCP %s:%d] UNHANDLED op=(%02x,%02x,%02x)"
                             " sub=0x%02x ver=0x%02x body=%d",
                             src_ip, src_port, *opcode, subtype, version,
                             len(body))
        except Exception as e:
            log.exception("[TCP %s:%d] handler error: %s",
                          src_ip, src_port, e)
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ---------- main server ----------

class MockKalay:
    def __init__(self, bind_addr: str, ports: list[int]) -> None:
        self.bind_addr = bind_addr
        # Back-compat for tests that pass an int and use `self.sock` / `self.bind`
        if isinstance(ports, int):
            ports = [ports]
        self.ports = ports
        self.socks: list[socket.socket] = []
        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socks.append(s)
        # Aliases for single-port tests
        self.sock = self.socks[0]
        self.bind = (bind_addr, ports[0])
        self.registry = Registry()

    def serve_forever(self) -> None:
        # Bind every socket; one thread per socket all sharing the same handler
        # and registry (registry is thread-safe).
        for sock, port in zip(self.socks, self.ports):
            sock.bind((self.bind_addr, port))
            log.info("listening on %s:%d (UDP)", self.bind_addr, port)

        if len(self.socks) == 1:
            self._serve_one(self.socks[0])
            return

        threads = []
        for sock in self.socks:
            t = threading.Thread(target=self._serve_one, args=(sock,), daemon=True)
            t.start()
            threads.append(t)
        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            log.info("shutting down")

    def _serve_one(self, sock: socket.socket) -> None:
        while True:
            try:
                data, src = sock.recvfrom(2048)
            except KeyboardInterrupt:
                log.info("shutting down")
                return
            except Exception as e:
                log.exception("recv failed: %s", e)
                continue
            try:
                self.handle(data, src, recv_sock=sock)
            except Exception as e:
                log.exception("handler failed for packet from %s: %s", src, e)

    def handle(self, data: bytes, src: tuple[str, int],
               recv_sock: socket.socket | None = None) -> None:
        src_ip, src_port = src
        # Reply via the socket the request arrived on so the source port
        # matches what the feeder expects (10001 vs 10240 etc.)
        if recv_sock is None:
            recv_sock = self.sock

        # Plaintext bootstrap
        if len(data) >= 4 and data[:4] == BOOTSTRAP_MAGIC:
            log.debug("[%s:%d] PT bootstrap (%d bytes)", src_ip, src_port, len(data))
            # Reply with STUN response telling the feeder its NAT'd endpoint.
            # On LAN, src_ip:src_port IS the endpoint catbro will use, so
            # we can just echo it back.
            resp = make_stun_response(src_ip, src_port)
            self._send(encrypt(resp), src, recv_sock)
            return

        if len(data) < 16:
            log.debug("[%s:%d] too short (%d) — ignoring", src_ip, src_port, len(data))
            return

        try:
            pt = decrypt(data)
        except Exception as e:
            log.warning("[%s:%d] decrypt failed (%d bytes): %s", src_ip, src_port, len(data), e)
            return

        if pt[0:2] != MAGIC:
            log.warning("[%s:%d] bad magic after decrypt: %s", src_ip, src_port, pt[:4].hex())
            return

        version = pt[2]
        opcode = (pt[8], pt[9], pt[10])
        body = pt[16:]
        log.debug("[%s:%d] version=0x%02x opcode=(%02x,%02x,%02x) wire_len=%d",
                  src_ip, src_port, version, *opcode, len(data))

        uid = extract_uid(body)

        # Dispatch
        if opcode == OP_DEV_STUN_REQ:
            self._handle_dev_stun_req(uid, src, body, recv_sock)
        elif opcode == OP_DEV_REG_FULL:
            self._handle_dev_reg_full(uid, src, body, recv_sock)
        elif opcode == OP_DEV_BULK_KEEP:
            self._handle_dev_keepalive(uid, src, body, recv_sock)
        elif opcode == OP_DEV_QUERY:
            self._handle_dev_query(uid, src, body, recv_sock)
        elif opcode == OP_DEV_SMALL_KEEP:
            self._handle_dev_small_keep(uid, src, body, recv_sock)
        elif opcode == OP_DEV_SESSION_NEXT:
            self._handle_dev_session_next(uid, src, body, recv_sock)
        elif opcode == OP_CLIENT_GET_RIP:
            self._handle_client_get_rip(uid, src, body, recv_sock)
        elif opcode == OP_CLIENT_REMOTE_REQ:
            self._handle_client_remote_req(uid, src, body, recv_sock)
        elif opcode == OP_CLIENT_REMOTE_ACK:
            self._handle_client_remote_ack(uid, src, body, recv_sock)
        elif opcode == OP_CLIENT_REMOTE_OK:
            self._handle_client_remote_ok(uid, src, body, recv_sock)
        elif opcode == OP_CLIENT_BCAST:
            self._handle_client_bcast(uid, src, body, recv_sock)
        else:
            log.info("[%s:%d] UNHANDLED opcode (%02x,%02x,%02x) ver=0x%02x uid=%s len=%d "
                     "(dropping; will need impl)",
                     src_ip, src_port, *opcode, version, uid, len(data))

    # --- device-side handlers ---

    def _handle_dev_stun_req(self, uid, src, body, sock):
        # STUN_REQ (opcode 07,10,18) sent to master-server port (10240) by
        # the feeder on boot. Real cloud replies with EDGE_LIST containing
        # (a) the feeder's STUN-echo external endpoint and (b) the relay
        # endpoints the feeder should use for REG_FULL.
        #
        # Client (phone) STUN_REQ has the AuthKey at body[20:36]; feeder
        # STUN_REQ doesn't. Only feeder-sourced packets should update the
        # registry — phone STUN_REQs would otherwise overwrite the feeder's
        # UID→IP mapping with the phone's IP.
        is_client = (len(body) >= 36 and
                     all(32 <= c < 127 for c in body[20:36]))
        log.info("[%s:%d] STUN_REQ uid=%s src=%s — replying with EDGE_LIST",
                 *src, uid, "client" if is_client else "feeder")
        if not uid:
            return
        if not is_client:
            self.registry.upsert(uid, src[0], src[1])
        mock_ip = self.bind_addr if self.bind_addr != "0.0.0.0" else "192.168.1.6"
        resp = make_edge_list(uid, mock_ip=mock_ip, mock_port=10001,
                              feeder_ip=src[0], feeder_port=src[1])
        self._send(encrypt(resp), src, sock)

    def _handle_dev_reg_full(self, uid, src, body, sock):
        # Try to pull the firmware string out (search for "3." anchor)
        firmware = None
        idx = body.find(b"3.")
        if idx > 0:
            end = body.find(b"\x00", idx)
            if end > idx:
                firmware = body[idx:end].decode("ascii", errors="replace")

        # Fall back to registry lookup by source IP if UID extraction failed
        if not uid:
            for known_uid, rec in self.registry.snapshot().items():
                if rec.lan_ip == src[0]:
                    uid = known_uid
                    log.debug("[%s:%d] REG_FULL: recovered uid=%s from src ip", *src, uid)
                    break

        log.info("[%s:%d] REG_FULL uid=%s firmware=%s", *src, uid, firmware)
        if uid:
            self.registry.upsert(uid, src[0], src[1], firmware=firmware)
            # Real cloud sends ONLY REG_ACK_VARIANT (opcode 21,01,41) in
            # response to REG_FULL — verified by 2026-05-27 feeder-realcloud
            # capture. Earlier we sent REG_ACK + EDGE_LIST + BIG_PUSH too;
            # those don't occur in the real flow and were causing the
            # feeder to never complete bootstrap.
            self._send(encrypt(make_register_ack_variant(uid)), src, sock)

    def _handle_dev_keepalive(self, uid, src, body, sock):
        log.debug("[%s:%d] KEEPALIVE uid=%s", *src, uid)
        if uid:
            self.registry.upsert(uid, src[0], src[1])
            self._send(encrypt(make_keepalive_ack(uid, src[0], src[1])), src, sock)

    def _handle_dev_query(self, uid, src, body, sock):
        log.info("[%s:%d] DEV_QUERY uid=%s (acking like keepalive)", *src, uid)
        if uid:
            self.registry.upsert(uid, src[0], src[1])
            self._send(encrypt(make_register_ack(uid)), src, sock)

    def _handle_dev_small_keep(self, uid, src, body, sock):
        # Feeder sends this as a STUN-like "still alive?" probe (opcode 03 80 3f).
        # Cloud's reply is the STUN response (opcode 04 80 4f) echoing the
        # observed source endpoint. Without this reply the feeder gets stuck
        # retrying SMALL_KEEPs and never progresses to registration.
        log.debug("[%s:%d] SMALL_KEEP — replying with STUN response", *src)
        resp = make_stun_response(src[0], src[1])
        self._send(encrypt(resp), src, sock)

    def _handle_dev_session_next(self, uid, src, body, sock):
        # Sent by the feeder immediately after REG_FULL. Without an ack the
        # feeder retries REG_FULL + SESSION_NEXT in a loop. Opcode 0c 01 14;
        # response opcode 0d 01 41 (guessed from req+1 / 14→41 pattern).
        log.info("[%s:%d] SESSION_NEXT uid=%s — sending ack", *src, uid)
        if uid:
            self.registry.upsert(uid, src[0], src[1])
            self._send(encrypt(make_session_next_ack(uid)), src, sock)

    # --- client-side handlers (catbro / TUTK clients) ---

    def _handle_client_get_rip(self, uid, src, body, sock):
        if not uid:
            log.warning("[%s:%d] GET_RIP without UID — dropping", *src)
            return
        rec = self.registry.get(uid)
        if not rec:
            log.warning("[%s:%d] GET_RIP for unknown uid %s — dropping", *src, uid)
            return
        # Extract the client's chosen sid8 from the GET_RIP body. bobobo1618's
        # session0.go puts sid8 at PACKET offset 100..107 → BODY offset 84..91.
        # First 4 bytes of sid8 (LE u32) = ClientRandomID that the feeder
        # will see in subsequent KNOCK2 packets.
        client_sid8 = b"\x10\x18\xf0\x80\x4a\x2d\x7c\x87"  # fallback (hardcoded)
        if len(body) >= 92:
            client_sid8 = bytes(body[84:92])
        client_random_id = struct.unpack("<I", client_sid8[:4])[0]
        log.info("[%s:%d] GET_RIP uid=%s sid8=%s rid=%u → %s:%d",
                 *src, uid, client_sid8.hex(), client_random_id,
                 rec.lan_ip, rec.lan_port)
        # 1. Reply to the client (catbro) with the feeder's endpoint and echo
        #    the sid8 the client chose, so its subsequent KNOCK2 matches.
        resp = make_lookup_response(uid, rec.lan_ip, rec.lan_port,
                                    sid8=client_sid8)
        self._send(encrypt(resp), src, sock)
        # 2. Send MSG_P2P_PUNCH_TO2 to the feeder. Per Ghidra disassembly of
        #    libIOTCAPIsT.so (FUN_00148634), this populates gPreSessionInfo
        #    with the client's RandomID — without it the feeder drops every
        #    incoming KNOCK2 silently.
        #
        # Send PUNCH_TO2 directly from our master-listening socket (port
        # 10001). That gives the packet a natural source of
        # 192.168.1.6:10001 — which matches the relay endpoint we
        # advertised to the feeder in EDGE_LIST. The feeder appears to
        # validate PUNCH_TO2 source against the relay it registered with,
        # so this is what it expects.
        #
        # (Earlier we routed PUNCH_TO2 via a separate socket on 10099 +
        # SNAT to spoof a real cloud IP. That path failed because: (a) the
        # feeder rejected the spoofed source — it only trusts the relay
        # it actually registered with; and (b) trying to SNAT to a port
        # that's locally bound returned EPERM. The simpler "send from the
        # listener" approach works.)
        client_ip_for_feeder = _client_ip_for_punch(src[0])
        if client_ip_for_feeder != src[0]:
            log.info("  ↳ rewriting client IP %s → %s (docker bridge → host LAN)",
                     src[0], client_ip_for_feeder)
        punch = make_punch_to2(uid, client_random_id=client_random_id,
                               client_wan_ip=client_ip_for_feeder,
                               client_wan_port=src[1],
                               session_token=client_sid8)
        feeder_addr = (rec.lan_ip, rec.lan_port)
        self._send(encrypt(punch), feeder_addr, sock)
        log.info("  → sent PUNCH_TO2 to feeder %s for client %s:%d rid=%u",
                 feeder_addr, *src, client_random_id)

    def _handle_client_remote_req(self, uid, src, body, sock):
        log.info("[%s:%d] REMOTE_REQ uid=%s (acking)", *src, uid)
        if uid:
            self._send(encrypt(make_register_ack(uid)), src, sock)

    def _handle_client_remote_ack(self, uid, src, body, sock):
        log.info("[%s:%d] REMOTE_ACK uid=%s", *src, uid)

    def _handle_client_remote_ok(self, uid, src, body, sock):
        log.info("[%s:%d] REMOTE_OK uid=%s", *src, uid)

    def _handle_client_bcast(self, uid, src, body, sock):
        log.info("[%s:%d] CLIENT_BCAST uid=%s", *src, uid)

    # --- io ---

    def _send(self, data: bytes, dst: tuple[str, int],
              sock: socket.socket | None = None) -> None:
        sock = sock or self.sock
        try:
            sock.sendto(data, dst)
        except Exception as e:
            log.exception("sendto %s failed: %s", dst, e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, action="append",
                    help="UDP port to listen on; repeat for multiple "
                         "(default: --port 10001 --port 10240)")
    ap.add_argument("--tcp-port", type=int, default=None,
                    help="Also listen for Kalay-over-TCP on this port"
                         " (typical: 80). Required for AV streaming.")
    ap.add_argument("--av-dump-dir", type=str, default=None,
                    help="When set, append received AV chunks to"
                         " <dir>/<UID>.bin (raw Kalay AV payloads).")
    ap.add_argument("--seed-feeder", action="append", default=[],
                    metavar="UID:IP:PORT",
                    help="Pre-populate the registry with UID→IP:PORT."
                         " Useful when feeders don't proactively check"
                         " in but their LAN IPs are known statically."
                         " Repeatable.")
    ap.add_argument("-v", "--verbose", action="count", default=0)
    args = ap.parse_args()

    level = logging.WARNING - 10 * args.verbose
    logging.basicConfig(
        level=max(level, logging.DEBUG),
        format="%(asctime)s %(levelname)-7s %(message)s",
    )

    ports = args.port or [10001, 10240]
    srv = MockKalay(args.bind, ports)

    for spec in args.seed_feeder:
        try:
            uid, ip, port = spec.split(":")
            srv.registry.upsert(uid, ip, int(port))
            log.info("seeded registry: %s → %s:%s", uid, ip, port)
        except ValueError:
            log.error("bad --seed-feeder %r (want UID:IP:PORT)", spec)
            return 2

    tcp_srv = None
    if args.tcp_port is not None:
        dump_dir = Path(args.av_dump_dir) if args.av_dump_dir else None
        av = AVStream(dump_dir=dump_dir)
        tcp_srv = MockKalayTCP(args.bind, args.tcp_port, av,
                               registry=srv.registry)
        t = threading.Thread(target=tcp_srv.serve_forever, daemon=True)
        t.start()

    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
