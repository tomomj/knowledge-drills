FROM node:24-bookworm-slim AS build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ARG VITE_FIREBASE_API_KEY=""
ENV VITE_FIREBASE_API_KEY=${VITE_FIREBASE_API_KEY}
ARG VITE_FIREBASE_AUTH_DOMAIN=""
ENV VITE_FIREBASE_AUTH_DOMAIN=${VITE_FIREBASE_AUTH_DOMAIN}
ARG VITE_FIREBASE_PROJECT_ID=""
ENV VITE_FIREBASE_PROJECT_ID=${VITE_FIREBASE_PROJECT_ID}
ARG VITE_FIREBASE_APP_ID=""
ENV VITE_FIREBASE_APP_ID=${VITE_FIREBASE_APP_ID}

RUN npm run build

FROM nginx:stable-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 8080
