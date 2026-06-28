FROM python:3.11-slim

WORKDIR /app

# System deps for OpenCV + video
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    libgl1-mesa-glx \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download YOLO model at build time if not mounted
RUN python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')" || true

CMD ["python", "main.py", "--camera-id", "${CAMERA_ID}"]
