FROM node:24-alpine
WORKDIR /workspace/client
RUN npm install -g pnpm@10
COPY client/package.json client/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY client ./
RUN chown -R node:node /workspace
USER node
EXPOSE 5173
CMD ["pnpm", "dev"]
