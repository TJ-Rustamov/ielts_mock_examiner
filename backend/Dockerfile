FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg build-essential espeak-ng \
    && rm -rf /var/lib/apt/lists/*

ARG INSTALL_VOICE=true

COPY requirements-core.txt requirements-voice.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-core.txt
RUN if [ "$INSTALL_VOICE" = "true" ]; then pip install --no-cache-dir -r requirements-voice.txt; fi

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py bootstrap_admin && daphne -b 0.0.0.0 -p 8000 ielts_backend.asgi:application"]
