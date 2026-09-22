FROM docker:29.4.0-dind

RUN apk add --no-cache bash git make python3 py3-pip gcc musl-dev python3-dev libffi-dev openssl-dev cargo
RUN python3 -m venv /opt/validation
ENV PATH="/opt/validation/bin:$PATH" USER=root
COPY ci/requirements.txt ci/collections.yml /opt/validation-inputs/
RUN pip install --no-cache-dir -r /opt/validation-inputs/requirements.txt \
    && ansible-galaxy collection install -r /opt/validation-inputs/collections.yml

WORKDIR /workspace
COPY . /workspace
ENTRYPOINT ["bash", "/workspace/ci/check"]
