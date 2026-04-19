FROM node:20-alpine AS dev
WORKDIR /app
RUN corepack enable
COPY package.json ./
RUN pnpm install --prefer-offline || pnpm install
COPY . .
EXPOSE 80
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "80"]


FROM node:20-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY . .
RUN pnpm build


FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
