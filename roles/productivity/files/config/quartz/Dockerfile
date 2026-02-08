FROM node:22-alpine

RUN apk add --no-cache git nginx coreutils

# Clone and install Quartz
WORKDIR /quartz
RUN git clone --depth 1 https://github.com/jackyzha0/quartz.git . && npm ci

# nginx config
RUN mkdir -p /run/nginx
COPY nginx.conf /etc/nginx/http.d/default.conf

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
