# Use the official Python image.
FROM python:3.11-slim

# Set the working directory in the container.
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y curl lynx && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy the project files.
COPY pyproject.toml .

# Install dependencies.
RUN uv pip compile pyproject.toml -o requirements.txt
RUN uv pip install --system -r requirements.txt

# Copy the rest of the application code.
COPY . .

# Set the command to run the application.
CMD ["python", "run.py"]
