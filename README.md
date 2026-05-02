# IELTS Mock Examiner

Full-stack IELTS practice platform with:
- `backend`: Django API for auth, writing, speaking, admin, and AI integrations
- `frontend`: React + Vite client UI
- `docker-compose.yml`: one-command local stack (backend + frontend)

## Project Structure

```text
.
├─ backend/
├─ frontend/
├─ models/
├─ docker-compose.yml
└─ .gitignore
```

## Quick Start (Docker)

1. Create backend env file:
```powershell
Copy-Item backend/.env.example backend/.env
```

2. Fill required values in `backend/.env` (especially `GEMINI_API_KEY`).

3. Start services:
```powershell
docker compose up -d --build
```

4. Open:
- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`

5. Stop services:
```powershell
docker compose down
```

## Local Development (Without Docker)

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend expects backend at `http://localhost:8000` by default (`VITE_API_BASE_URL`).

## Environment

Use:
- `backend/.env.example` as the template
- `backend/.env` for local secrets (ignored by git)

Minimum required:
- `DJANGO_SECRET_KEY`
- `GEMINI_API_KEY`

Optional voice-related settings are already documented in `backend/.env.example`.

## STT / TTS Model Links

This project is configured for these model paths by default:
- `WHISPER_MODEL_SIZE=/models/faster-whisper-base.en`
- `KOKORO_MODEL_PATH=/models/Kokoro-82M/kokoro-v1_0.pth`

Download/source links:
- STT (Whisper, CTranslate2): https://huggingface.co/Systran/faster-whisper-base.en
- TTS (Kokoro-82M): https://huggingface.co/hexgrad/Kokoro-82M
- Kokoro project repo: https://github.com/hexgrad/kokoro

Place downloaded files under `models/` so Docker can mount them at `/models`.

## Useful Commands

```powershell
# View backend logs
docker logs --tail 120 ielts_backend

# View frontend logs
docker logs --tail 80 ielts_frontend
```

## Notes

- Frontend source is in `frontend` (not `fromtend`).
- Docker compose frontend build context is `./frontend`.
- Large model files should stay under `models/` and not be committed unless explicitly intended.

## License

This project is licensed under the [GNU Affero General Public License v3.0 (AGPLv3)](LICENSE). 
This strongly copyleft license is intended to ensure that the complete source code of this software remains open and freely accessible. Any modifications, improvements, or services (like SaaS or cloud hosting) built upon this project must also be open-sourced under the same terms. This restricts proprietary and closed-source profiteering off the software.
