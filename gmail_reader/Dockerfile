# Use the official Python image.
FROM python:3.11-slim

# Set the working directory in the container.
WORKDIR /app

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy the project files.
COPY pyproject.toml .

# Install dependencies.
RUN uv pip install --system -r <(uv pip compile pyproject.toml)

# Copy the rest of the application code.
COPY run.py .

# Set the command to run the application.
CMD ["python", "run.py"]
