# Strudel - Live Coding Music Environment
FROM node:20-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git && corepack enable
RUN git clone --depth 1 https://codeberg.org/uzu/strudel.git .
RUN pnpm install && pnpm run build

FROM nginx:alpine

COPY --from=builder /app/website/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
