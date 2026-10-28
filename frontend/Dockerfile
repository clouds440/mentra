FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=http://localhost:8000
ARG MENTRA_RELEASE=false
ENV VITE_API_URL=${VITE_API_URL}
RUN MENTRA_RELEASE=${MENTRA_RELEASE} node scripts/validate-release.mjs && npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:782bb89768cc87b7f95c18b95baa1af250e5d451f26794f59363540161147c01

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

ARG MENTRA_REVISION=unknown
LABEL org.opencontainers.image.revision=${MENTRA_REVISION}
