# Strudel - Live Coding Music Environment
# Based on the official strudel repository
FROM node:20-alpine AS builder

WORKDIR /app

# Install git for cloning the repository
RUN apk add --no-cache git

# Clone the Strudel repository
RUN git clone --depth 1 https://github.com/tidalcycles/strudel.git .

# Install dependencies and build
RUN npm ci && npm run build

# Production stage
FROM nginx:alpine

# Copy built assets to nginx
COPY --from=builder /app/packages/website/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
