FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
EXPOSE 3000
CMD ["npm", "run", "dev"]
