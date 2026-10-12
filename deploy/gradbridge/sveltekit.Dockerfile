# GradBridge web front ends (SvelteKit + adapter-node). One file for both apps:
#   build context site/       -> job seeker site
#   build context recruiter/  -> recruiter app
# PUBLIC_* values are compiled in ($env/static/public), so pass them as build
# args for the environment the image is for.
FROM node:24-slim AS build
RUN npm install -g pnpm@10
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG PUBLIC_API_BASE_URL
ARG PUBLIC_SITE_URL
ARG PUBLIC_RECRUITER_URL
ARG PUBLIC_JOBSEEKER_URL
ENV PUBLIC_API_BASE_URL=$PUBLIC_API_BASE_URL \
    PUBLIC_SITE_URL=$PUBLIC_SITE_URL \
    PUBLIC_RECRUITER_URL=$PUBLIC_RECRUITER_URL \
    PUBLIC_JOBSEEKER_URL=$PUBLIC_JOBSEEKER_URL
RUN pnpm run build && pnpm prune --prod

FROM node:24-slim
# adapter-node: set ORIGIN (the public URL) at run time so form actions pass
# SvelteKit's CSRF origin check behind a proxy.
ENV NODE_ENV=production PORT=3000 HOST=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /app/package.json ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/build ./build
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then((r) => process.exit(r.status < 500 ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "build"]
