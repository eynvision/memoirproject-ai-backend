#FROM python:3.12-slim

WORKDIR /app

# Install deps first (Docker caches this layer if requirements don't change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Hugging Face Spaces requires the app to listen on port 7860
EXPOSE 8000

# Start the server on that port, binding to all interfaces
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
