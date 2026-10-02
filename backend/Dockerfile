# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# The voice and exam wheels are large (faster-whisper, torch, onnxruntime,
# opencv). pip default of 15s times out on a slow link mid-download.
ENV PIP_DEFAULT_TIMEOUT=180
ENV PIP_RETRIES=10

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential espeak-ng \
    && rm -rf /var/lib/apt/lists/*

ARG INSTALL_VOICE=true
ARG INSTALL_EXAMS=true

COPY requirements-core.txt requirements-voice.txt requirements-exams.txt requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-core.txt
RUN --mount=type=cache,target=/root/.cache/pip if [ "$INSTALL_VOICE" = "true" ]; then pip install -r requirements-voice.txt; fi
RUN --mount=type=cache,target=/root/.cache/pip if [ "$INSTALL_EXAMS" = "true" ]; then pip install -r requirements-exams.txt; fi

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py bootstrap_admin && daphne -b 0.0.0.0 -p 8000 ielts_backend.asgi:application"]
