#!/usr/bin/env python3
"""
Python port of the TUTK 'Charlie' cipher used by Petlibro / Kalay.

Reference implementation: github.com/bobobo1618/go2rtc/pkg/tutk/crypto.go

The cipher operates on 16-byte blocks with the constant key
"Charlie is the designer of P2P!!". Encryption and decryption are NOT
the same operation (the rotations are signed differently and the byte-swap
is applied at a different phase), so we expose both directions.

Also includes XXTEA, which the Go code uses for an inner layer (purpose
not yet confirmed for our master-server protocol).
"""
from __future__ import annotations
import struct


CHARLIE = b"Charlie is the designer of P2P!!"  # 32 bytes; we use first 16

# Byte-swap permutation applied to each 16-byte block.
# `swap16[i]` says: dst[i] = src[swap16[i]]
SWAP16 = [11, 9, 8, 15, 13, 10, 12, 14, 2, 1, 5, 0, 6, 4, 7, 3]


def _rotl32(x: int, n: int) -> int:
    n &= 31
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _swap_block(src: bytes) -> bytes:
    n = len(src)
    if n != 16:
        # Fallback for non-block-aligned tails: identity. Matches Go code's
        # default branch for n that isn't 2/4/8/16.
        return bytes(src)
    return bytes(src[SWAP16[i]] for i in range(16))


def reverse_trans_code_partial(src: bytes) -> bytes:
    """Decrypt a buffer using the Charlie cipher (matches Go's ReverseTransCodePartial)."""
    n = len(src)
    out = bytearray(n)
    src = bytes(src)
    src_off = 0

    while n >= 16:
        block = src[src_off:src_off + 16]
        # 1. rotate-left each 32-bit word by (i+3) where i in {0,4,8,12}
        tmp = bytearray(16)
        for i in (0, 4, 8, 12):
            x = struct.unpack_from('<I', block, i)[0]
            struct.pack_into('<I', tmp, i, _rotl32(x, i + 3))

        # 2. byte-swap
        swapped = _swap_block(bytes(tmp))
        out[src_off:src_off + 16] = swapped

        # 3. XOR with charlie[0..16]
        for i in range(16):
            tmp[i] = out[src_off + i] ^ CHARLIE[i]

        # 4. rotate-left each word by (i+1)
        for i in (0, 4, 8, 12):
            x = struct.unpack_from('<I', tmp, i)[0]
            struct.pack_into('<I', out, src_off + i, _rotl32(x, i + 1))

        src_off += 16
        n -= 16

    if n > 0:
        # Tail: swap (identity for non-aligned), then XOR with charlie[0..n]
        tail = _swap_block(src[src_off:src_off + n])
        for i in range(n):
            out[src_off + i] = tail[i] ^ CHARLIE[i]

    return bytes(out)


def reverse_trans_code_blob(src: bytes) -> bytes:
    """
    Decrypt a full packet, honoring the partial-encryption flag.

    Matches Go's ReverseTransCodeBlob: decrypts the first 16-byte header
    unconditionally; if header byte 3 has bit 0 set, only the next 48 bytes
    are encrypted (total 64 enc'd) and the rest is plaintext. Otherwise the
    whole packet is encrypted.
    """
    if len(src) < 16:
        return reverse_trans_code_partial(src)

    out = bytearray(len(src))
    header = reverse_trans_code_partial(src[:16])
    out[:16] = header

    if len(src) > 16:
        if header[3] & 1:
            remaining = len(src) - 16
            decrypt_len = min(remaining, 48)
            if decrypt_len > 0:
                decrypted = reverse_trans_code_partial(src[16:16 + decrypt_len])
                out[16:16 + decrypt_len] = decrypted
            if remaining > 48:
                out[64:] = src[64:]
        else:
            decrypted = reverse_trans_code_partial(src[16:])
            out[16:] = decrypted
    return bytes(out)


def trans_code_partial(src: bytes) -> bytes:
    """Encrypt a buffer using the Charlie cipher (matches Go's TransCodePartial)."""
    n = len(src)
    out = bytearray(n)
    src = bytes(src)
    src_off = 0

    while n >= 16:
        block = src[src_off:src_off + 16]
        # 1. rotate-left each word by (-i-1) == rotate-right by (i+1)
        tmp = bytearray(16)
        for i in (0, 4, 8, 12):
            x = struct.unpack_from('<I', block, i)[0]
            struct.pack_into('<I', tmp, i, _rotl32(x, -(i + 1)))

        # 2. XOR with charlie[0..16]
        for i in range(16):
            tmp[i] ^= CHARLIE[i]

        # 3. byte-swap (note: in encrypt, swap is applied AFTER xor)
        swapped = _swap_block(bytes(tmp))
        tmp = bytearray(swapped)

        # 4. rotate-left each word by (-i-3) == rotate-right by (i+3)
        for i in (0, 4, 8, 12):
            x = struct.unpack_from('<I', tmp, i)[0]
            struct.pack_into('<I', out, src_off + i, _rotl32(x, -(i + 3)))

        src_off += 16
        n -= 16

    if n > 0:
        tmp = bytearray(n)
        for i in range(n):
            tmp[i] = src[src_off + i] ^ CHARLIE[i]
        out[src_off:src_off + n] = _swap_block(bytes(tmp))

    return bytes(out)


def trans_code_blob(src: bytes) -> bytes:
    """Encrypt a full packet, honoring the partial-encryption flag in src[3]&1."""
    if len(src) < 16:
        return trans_code_partial(src)

    out = bytearray(len(src))
    header = trans_code_partial(src[:16])
    out[:16] = header

    if len(src) > 16:
        if src[3] & 1:
            remaining = len(src) - 16
            encrypt_len = min(remaining, 48)
            if encrypt_len > 0:
                encrypted = trans_code_partial(src[16:16 + encrypt_len])
                out[16:16 + encrypt_len] = encrypted
            if remaining > 48:
                out[64:] = src[64:]
        else:
            encrypted = trans_code_partial(src[16:])
            out[16:] = encrypted
    return bytes(out)


# --- self-test ---
if __name__ == "__main__":
    import sys

    # Round-trip test: encrypt(decrypt(x)) should NOT equal x, but
    # decrypt(encrypt(x)) SHOULD. The Go code's TransCode and ReverseTransCode
    # are mirror operations.
    test = b"Hello, world! This is a TUTK test message exceeding 16 bytes."
    enc = trans_code_blob(test)
    dec = reverse_trans_code_blob(enc)
    print(f"plain:   {test.hex()}")
    print(f"encrypt: {enc.hex()}")
    print(f"decrypt: {dec.hex()}")
    assert dec == test, f"round-trip failed!\n  in:  {test.hex()}\n  out: {dec.hex()}"
    print(f"round-trip OK (len={len(test)})")

    # Also test a 16-byte (single-block) buffer
    test16 = b"sixteen bytes!!!"
    assert reverse_trans_code_blob(trans_code_blob(test16)) == test16
    print("round-trip OK (len=16, single block)")

    # And a sub-16 buffer
    test4 = b"abcd"
    assert reverse_trans_code_blob(trans_code_blob(test4)) == test4
    print("round-trip OK (len=4, partial only)")
