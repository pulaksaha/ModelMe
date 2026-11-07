FROM node:24-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:24-alpine AS api
ENV NODE_ENV=production \
    API_PORT=3001 \
    FRONTEND_DIST=../../../frontend/dist
WORKDIR /app/services/api
COPY services/api/package.json services/api/package-lock.json ./
RUN npm ci --omit=dev
COPY services/api/src ./src
COPY --from=frontend-build /frontend/dist /app/frontend/dist
USER node
EXPOSE 3001
CMD ["npm", "start"]
