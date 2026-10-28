# phpBB board application image.
# Official phpBB release tarball, pinned by SHA-256. Source revision and
# rebuild policy: roles/phpbb/README.md.
FROM php:8.4.27-fpm-alpine3.24

ARG PHPBB_VERSION=3.3.19
ARG PHPBB_SHA256=66f35fa3d9bf3b90269205bbb281e1156727a0014eea344fe15f9c7376b78c66

# Runtime libraries for the bundled GD (PNG/JPEG/FreeType/WebP), intl, and
# zip extensions; curl and bzip2 for the pinned release download.
RUN apk add --no-cache \
        curl \
        bzip2 \
        libpng \
        libjpeg-turbo \
        freetype \
        libwebp \
        icu-libs \
        libzip

RUN apk add --no-cache --virtual .build-deps \
        libpng-dev \
        libjpeg-turbo-dev \
        freetype-dev \
        libwebp-dev \
        icu-dev \
        libzip-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
    && docker-php-ext-install -j"$(nproc)" gd mysqli pdo_mysql intl zip opcache \
    && apk del .build-deps

RUN set -eu; \
    curl -fsSL -o /tmp/phpbb.tar.bz2 \
      "https://download.phpbb.com/pub/release/3.3/${PHPBB_VERSION}/phpBB-${PHPBB_VERSION}.tar.bz2"; \
    echo "${PHPBB_SHA256}  /tmp/phpbb.tar.bz2" | sha256sum -c -; \
    mkdir -p /usr/share/phpbb; \
    tar -xjf /tmp/phpbb.tar.bz2 -C /tmp; \
    cp -a /tmp/phpBB3/. /usr/share/phpbb/; \
    rm -rf /tmp/phpBB3 /tmp/phpbb.tar.bz2; \
    chown -R root:root /usr/share/phpbb

COPY phpbb-health.php /usr/share/phpbb/health.php
COPY phpbb-ensure.php /usr/local/bin/phpbb-ensure.php
COPY phpbb-update /usr/local/bin/phpbb-update
COPY phpbb-init /usr/local/bin/phpbb-init
COPY phpbb-entrypoint /usr/local/bin/phpbb-entrypoint

RUN chmod 0755 /usr/local/bin/phpbb-init /usr/local/bin/phpbb-entrypoint \
        /usr/local/bin/phpbb-update \
    && chmod 0644 /usr/share/phpbb/health.php /usr/local/bin/phpbb-ensure.php

# FPM master runs as root (the entrypoint installs and repairs ownership);
# workers run as www-data through the base image pool.
ENTRYPOINT ["/usr/local/bin/phpbb-entrypoint"]
CMD ["php-fpm"]
