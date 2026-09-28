# Stage 1: build the React app into static files.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Baked in at build time: links to the Temporal Web UI (opened by your browser).
ARG VITE_TEMPORAL_UI_URL=http://localhost:8233
ARG VITE_TEMPORAL_NAMESPACE=default
ENV VITE_TEMPORAL_UI_URL=$VITE_TEMPORAL_UI_URL \
    VITE_TEMPORAL_NAMESPACE=$VITE_TEMPORAL_NAMESPACE
RUN npm run build

# Stage 2: serve the static files with nginx; nginx also proxies /api to FastAPI.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
