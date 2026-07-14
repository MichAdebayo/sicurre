FROM node:22-bookworm-slim AS deps

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS build

COPY index.html tsconfig.json vite.config.ts ./
COPY src/app ./src/app
RUN npm run build

FROM node:22-bookworm-slim AS web

WORKDIR /app
ENV NODE_ENV=production \
    PORT=5173 \
    APP_DIST_DIR=/app/dist

COPY --from=build /app/dist ./dist
COPY scripts/app/*.mjs ./scripts/app/

EXPOSE 5173

CMD ["node", "scripts/app/container_server.mjs"]

FROM deps AS auth

WORKDIR /app
ENV NODE_ENV=production \
    SICURRE_BETTER_AUTH_PORT=3005

RUN mkdir -p data/local

COPY auth-service ./auth-service

EXPOSE 3005

CMD ["./node_modules/.bin/tsx", "auth-service/main.ts"]
