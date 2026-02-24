# ── NSE Trader Frontend (Next.js) ──────────────────────────────────
# Two-stage: install+build, then serve with next start.
# ───────────────────────────────────────────────────────────────────

# Stage 1: Install + build
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json* yarn.lock* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

COPY . .

# Backend URL used by next.config.mjs rewrites (build-time)
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=${BACKEND_URL}

RUN npm run build

# Stage 2: Production
FROM node:20-alpine
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built app + node_modules + config
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/next.config.mjs ./

USER nextjs

EXPOSE 3000

# Runtime BACKEND_URL for rewrites
ENV BACKEND_URL=http://backend:8000

CMD ["npx", "next", "start", "-p", "3000"]
