# AI Models Directory

This directory is intended to store the downloaded AI models required to run the local STT (Speech-to-Text) and TTS (Text-to-Speech) pipelines.

Since the models are large binary files, they are **ignored by Git** and are not checked into the repository (with the exception of this README and the `.keep` file). You must download and place the models here manually or via a setup script before running the application locally or in Docker.

## Required Directory Structure

Once the models are downloaded, your `models/` directory should look exactly like this:

```text
models/
├── faster-whisper-base.en/
│   ├── config.json
│   ├── model.bin
│   ├── tokenizer.json
│   └── vocabulary.json
├── Kokoro-82M/
│   ├── config.json
│   ├── kokoro-v1_0.pth
│   └── voices/
│       ├── af_heart.pt
│       ├── af_alloy.pt
│       └── ... (other voice tensors)
├── .keep
└── README.md
```

## How to Get the Models

### 1. Faster-Whisper (STT)
The application expects the `faster-whisper-base.en` CTranslate2 model.
You can download the files from HuggingFace:
[https://huggingface.co/Systran/faster-whisper-base.en/tree/main](https://huggingface.co/Systran/faster-whisper-base.en/tree/main)

Download the `.bin` and `.json` files and place them inside `models/faster-whisper-base.en/`.

### 2. Kokoro TTS
The application expects the `Kokoro-82M` model weights and its voices.
You can download them from HuggingFace:
[https://huggingface.co/hexgrad/Kokoro-82M/tree/main](https://huggingface.co/hexgrad/Kokoro-82M/tree/main)

Download `kokoro-v1_0.pth`, `config.json`, and the entire `voices` folder. Place them inside `models/Kokoro-82M/`.

## Environment Variables
Ensure your `.env` file points to these models correctly:
```env
WHISPER_MODEL_SIZE=/models/faster-whisper-base.en
KOKORO_MODEL_PATH=/models/Kokoro-82M/kokoro-v1_0.pth
```
*(Note: Inside the Docker container, the models directory is mounted to `/models`. If running purely locally without Docker, you may need to use absolute paths in your `.env` like `D:/university/models/Kokoro-82M/kokoro-v1_0.pth`)*
