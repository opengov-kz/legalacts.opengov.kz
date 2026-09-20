FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV FASTAPI_BASE_URL=http://api:8000
ENV API_KEY=build-placeholder
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Docker sets HOSTNAME to the container ID by default; the standalone server.js binds
# to `process.env.HOSTNAME || '0.0.0.0'`, so without this it silently binds to that
# container-ID "hostname" instead of all interfaces, and 127.0.0.1 (e.g. a healthcheck
# run inside the container) can't reach it even though external traffic still does.
ENV HOSTNAME="0.0.0.0"
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
