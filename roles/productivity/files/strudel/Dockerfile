# Strudel - Live Coding Music Environment
# Based on the official strudel repository
FROM node:20-alpine AS builder

WORKDIR /app

# Install git and enable corepack for pnpm
RUN apk add --no-cache git && corepack enable

# Clone the Strudel repository (moved from GitHub to Codeberg)
RUN git clone --depth 1 https://codeberg.org/uzu/strudel.git .

# Install dependencies and build using pnpm (project uses workspace:* protocol)
RUN pnpm install && pnpm run build

# Production stage
FROM nginx:alpine

# Copy built assets to nginx
COPY --from=builder /app/website/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
