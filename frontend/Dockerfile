FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Build-time values from the project `.env` (passed as build args by docker compose).
ARG API_PREFIX=/api/v1
ARG VITE_API_URL=
ARG VITE_API_TIMEOUT_MS=60000
ENV API_PREFIX=$API_PREFIX VITE_API_URL=$VITE_API_URL VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
# Runtime values; the image renders /etc/nginx/templates/*.template with these on start.
ENV NGINX_PORT=8080 \
    API_UPSTREAM=http://api:8000 \
    API_PREFIX=/api/v1
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- "http://127.0.0.1:${NGINX_PORT}/" >/dev/null || exit 1
