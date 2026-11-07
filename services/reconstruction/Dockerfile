FROM python:3.12-slim
ARG BLENDER_VERSION=5.2.3
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BLENDER_EXECUTABLE=/opt/blender/blender \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils \
      libgl1 libegl1 libxi6 libxrender1 libxfixes3 libxkbcommon0 \
      libxxf86vm1 libsm6 libice6 libxext6 libx11-6 libxcb1 \
      libxrandr2 libxinerama1 libxcursor1 libxcomposite1 libasound2 \
      libfontconfig1 libfreetype6 libdbus-1-3 libgomp1 libglib2.0-0 \
      libwayland-client0 libharfbuzz0b \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://download.blender.org/release/Blender5.2/blender-${BLENDER_VERSION}-linux-x64.tar.xz" -o /tmp/blender.tar.xz \
    && mkdir -p /opt/blender \
    && tar -xJf /tmp/blender.tar.xz --strip-components=1 -C /opt/blender \
    && rm /tmp/blender.tar.xz

WORKDIR /app
COPY backend/requirements.lock.txt /app/backend/requirements.lock.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.lock.txt
COPY backend/ /app/backend/
COPY blender/ /app/blender/
COPY reconstruction/ /app/reconstruction/
COPY assets/base_human/base_human.blend /app/assets/base_human/base_human.blend
RUN mkdir -p /app/input /app/output /app/storage/generated \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app/input /app/output /app/storage

USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
