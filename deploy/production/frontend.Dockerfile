FROM node:20-alpine

WORKDIR /app

COPY frontend/package*.json /app/
RUN npm install

COPY frontend /app

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start", "--", "-p", "3000"]
