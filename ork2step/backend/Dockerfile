FROM condaforge/miniforge3:latest

# System dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglu1-mesa \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install cadquery via conda - only reliable method on ARM64
RUN conda install -y -c cadquery -c conda-forge cadquery python=3.11 && \
    conda clean -afy

# Install web framework deps
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    "uvicorn[standard]==0.29.0" \
    python-multipart==0.0.9 \
    lxml \
    pydantic==2.7.1

WORKDIR /app
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
