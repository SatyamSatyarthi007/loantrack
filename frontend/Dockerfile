# Multi-stage Dockerfile for LoanTrack Static Frontend
# Stage 1: Minimal stage preparing static assets (no Node build step needed for plain HTML/JS)
FROM alpine:3.20 AS builder

WORKDIR /src
COPY index.html .
COPY nginx.conf .

# Stage 2: Runtime using pinned unprivileged Nginx (runs on port 8080 as non-root user 101)
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Copy custom Nginx configuration to override default site
COPY --from=builder /src/nginx.conf /etc/nginx/conf.d/default.conf

# Copy static frontend assets to standard Nginx webroot
COPY --from=builder /src/index.html /usr/share/nginx/html/index.html

# Expose unprivileged non-root port 8080
EXPOSE 8080

# Run Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
