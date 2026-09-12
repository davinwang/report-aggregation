# React SPA — multi-stage: build with Node, serve with nginx.
# nginx proxies /api and /health to the backend container (mirrors the vite dev proxy).
# ---- Stage 1: build ----
FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ---- Stage 2: runtime ----
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/frontend/nginx.conf /etc/nginx/conf.d/default.conf
# Normalize CRLF (Windows checkouts) so nginx parses the config cleanly.
RUN sed -i 's/\r$//' /etc/nginx/conf.d/default.conf

EXPOSE 80
