# Use the official Python image.
FROM python:3.12-slim

# Set the working directory in the container.
WORKDIR /app

# Install mcp-sqlite
RUN pip install mcp-sqlite

# Copy metadata file
COPY metadata.yml .

# Expose the port the app runs on
EXPOSE 8080

# Set the command to run the application.
CMD ["mcp-sqlite", "-v", "--metadata", "metadata.yml", "/data/gastos.db"]