FROM --platform=linux/arm64 python:3.11-slim

# CadQuery system dependencies (ARM-compatible package names)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglu1-mesa \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
