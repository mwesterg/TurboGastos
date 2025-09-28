# Stage 1: Build the React application
FROM node:20-alpine AS build

WORKDIR /app

# Copy package.json and package-lock.json
COPY package.json ./

# Install dependencies
RUN npm install

# Make the build argument available in the container
ARG REACT_APP_API_KEY
# Create a .env file with the API key
RUN echo "REACT_APP_API_KEY=${REACT_APP_API_KEY}" > .env

# Copy the rest of the application source code
COPY . .

# Build the application
RUN npm run build

# Stage 2: Serve the application using Nginx
FROM nginx:stable-alpine

# Copy the built application from the build stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy a custom Nginx configuration
# COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]