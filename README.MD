# Prescription Assistant

A fully local, private prescription knowledge base with OCR and AI chat. Parents can store their child's prescription records and ask natural-language questions over them — everything runs on your own machine, no cloud accounts or API keys required.

> **Disclaimer:** This application summarizes your saved records only. It does not provide medical advice, dosing recommendations, or diagnoses. Always consult a qualified healthcare provider.

## Features

- **Upload & extract** — snap a photo of a prescription; Tesseract OCR pulls the text and a local LLM structures it into fields (doctor, date, diagnosis, medications, dosage, duration) for you to review and correct before saving.
- **Manual entry** — add records by hand without a photo.
- **Ask** — chat interface backed by semantic search (ChromaDB + sentence-transformers) over your saved records; the LLM answers from your data only.
- **Records** — browse everything you've saved.
- 100% offline — OCR, embeddings, and the LLM (Ollama) all run locally. Nothing leaves your machine.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite + TypeScript, served by nginx |
| Backend | FastAPI + uvicorn |
| OCR | Tesseract (inside the backend container) |
| LLM | Ollama, running `llama3.2` on the host machine |
| Vector search | ChromaDB + `sentence-transformers` (`all-MiniLM-L6-v2`) |
| Storage | Flat JSON file (`data/prescriptions.json`), mounted as a volume |
| Orchestration | Docker Compose |

## Architecture

```
Browser (React SPA)
   |  HTTP requests
   v
nginx (frontend container -- port 3000)
   |  /api/* proxied internally
   v
FastAPI backend (port 8000 -- internal only)
   |
   +--[POST /api/ocr]-----------> Tesseract OCR   (inside backend image)
   |                                 v  raw text
   +--[extraction.py]-----------> Ollama on host  (:11434)
   |                                 v  structured JSON
   +--[storage.py]---------------> prescriptions.json  (volume: ./data)
   |
   +--[rag.py]--------------------> ChromaDB  (persisted in ./data/chroma/)
   |                                 v  embeddings (sentence-transformers)
   +--[POST /api/chat]-----------> Ollama on host  (:11434, chat API)
```

Ollama is **not** containerized — it runs directly on your host machine, and the backend container reaches it via `host.docker.internal:11434`.

## Prerequisites

Install these before cloning the repo. You do **not** need Node.js or Python installed locally — both run inside Docker during the build.

| Tool | Where to get it | Verify |
|---|---|---|
| Docker Desktop | [docker.com/products/docker-desktop](https://docker.com/products/docker-desktop) | `docker --version` |
| Ollama | [ollama.com/download](https://ollama.com/download) | `ollama list` |
| `llama3.2` model | `ollama pull llama3.2` | shows up in `ollama list` (~2 GB) |

## Setup

```powershell
# 1. Clone the repo
git clone <your-repo-url> medical-assistant
cd medical-assistant

# 2. Make sure Ollama is running and has the model
ollama pull llama3.2
ollama list

# 3. Build and start everything
docker compose up --build
```

**First build note:** downloads base images plus the `sentence-transformers` embedding model (~90 MB) on first run — allow 10–20 minutes on a slow connection, and a few extra minutes on any rebuild unless you've added the Hugging Face cache volume described below.

Once it's up:

| URL | What you'll see |
|---|---|
| `http://localhost:3000` | The app — Ask / Records / Upload tabs |
| `http://localhost:8000/docs` | Swagger UI listing all backend routes |

To stop: `docker compose down` (your data in `./data` persists across restarts).

## Configuration

Environment values are currently set directly in `docker-compose.yml` under the `backend` service. `.env.example` documents what each one means if you want to break them out into a real `.env` file:

| Variable | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `/app/data` | Where prescription data lives inside the container |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Where the backend reaches Ollama on your host |
| `OLLAMA_MODEL` | `llama3.2` | Model used for both extraction and chat |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model for semantic search |
| `CHROMA_COLLECTION` | `prescriptions` | ChromaDB collection name |

## Project Structure

```
medical-assistant/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── config.py         # settings (paths, model names)
│       ├── models.py         # Pydantic schemas
│       ├── storage.py        # read/write prescriptions.json
│       ├── ocr.py            # image bytes -> text (Tesseract)
│       ├── extraction.py     # OCR text -> structured JSON (Ollama)
│       ├── rag.py            # vector search + chat answer (Ollama)
│       └── main.py           # FastAPI routes
├── frontend/
│   ├── Dockerfile             # multi-stage: npm build + nginx serve
│   ├── nginx.conf             # proxies /api to backend, SPA fallback
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx           # chat / records / upload UI
│       ├── api.ts            # fetch wrappers
│       ├── index.css
│       └── vite-env.d.ts
├── data/
│   └── prescriptions.json     # your records (persisted volume, gitignored)
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## Customizations from the base build

A few settings have been tuned beyond the original scaffold, based on real issues hit during testing:

- **`frontend/nginx.conf`** — the `/api/` location block sets `proxy_read_timeout`, `proxy_send_timeout`, and `proxy_connect_timeout` to `180s`. OCR + LLM extraction on a photo can take well past nginx's 60s default, which otherwise surfaces as a `504 Bad Gateway` in the browser even though the backend is still working.
- **`backend/app/rag.py`** — chat calls use Ollama's `/api/chat` endpoint with separate `system`/`user` messages, instead of one flat prompt to `/api/generate`. The system prompt explicitly frames answers as *reporting already-recorded history* rather than *giving medical advice*, which noticeably reduces the model refusing to state a dosage/duration that's already written in a saved record.
- **`docker-compose.yml`** — the backend service mounts an extra volume, `./data/hf-cache:/root/.cache/huggingface`, so the `sentence-transformers` embedding model persists across rebuilds instead of re-downloading (and delaying startup by several minutes) every time the backend image is rebuilt.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Error loading ASGI app. Could not import module "app.main"` | `main.py` doesn't exist yet, or you ran `up`/`run` without overriding the default `uvicorn` command | Expected before `main.py` is created; otherwise use `docker compose run --rm backend python -c "..."` to bypass the default CMD |
| `ModuleNotFoundError` for a file you just added | Source is baked into the image at build time, not live-mounted | `docker compose build backend` (or `--no-cache` for a clean rebuild), then rerun |
| `invalid mount config ... mount path must be absolute` | Missing colon in a `volumes:` entry in `docker-compose.yml` | Should read `./data:/app/data`, not `./data/app/data` |
| `504 Bad Gateway` / Gateway Timeout on OCR | nginx's default 60s proxy timeout is shorter than OCR + LLM extraction can take | Increase `proxy_read_timeout` etc. in `nginx.conf` (see Customizations above), then `docker compose build frontend` |
| `connect() failed (111: Connection refused)` in nginx logs, backend unreachable | Backend container crashed on startup (often a syntax error after editing `rag.py`/`extraction.py`) | `docker compose logs backend` for the traceback; fix and `docker compose up --build backend` |
| Backend takes ~5 minutes to come up after a rebuild | Embedding model re-downloading because its cache isn't persisted | Add the `hf-cache` volume mount described above |
| Chat says "Ollama is unavailable" | Ollama isn't running, or wrong model name | `ollama list` to confirm `llama3.2` is present; make sure Ollama is running before `docker compose up` |
| `Invoke-RestMethod` shows nothing for `/api/prescriptions` | PowerShell prints nothing for an empty array — this is expected, not an error | Confirm with `(Invoke-WebRequest ...).Content` or `| ConvertTo-Json` |

## Roadmap / Not Yet Implemented

This is currently a **single-user, local-only** application. Known gaps if this were to become a public multi-user webapp:

- No authentication, accounts, or per-user data isolation
- Storage is a flat JSON file + local Chroma index, not a real database
- Ollama runs on the host machine — not viable for a public deployment as-is
- OCR + extraction run synchronously in the request (fine locally, would need a background job queue under real concurrent load)
- No HTTPS/TLS, secrets management, or locked-down CORS policy

## License

Personal project — add a license here if you plan to open-source it.
