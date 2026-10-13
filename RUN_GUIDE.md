# Home Assistant: local setup and run guide

This guide starts the complete project on Windows: PostgreSQL, Ollama, the
FastAPI backend, the document worker, and the React frontend.

## 1. Install these prerequisites

- **Git** — downloads and manages the source code.
- **Python 3.12** — runs the backend and document worker. During installation,
  enable the option that adds Python/the `py` launcher to `PATH`.
- **Docker Desktop** — runs PostgreSQL 16 with the `pgvector` extension. Start
  Docker Desktop before running the project.
- **Ollama for Windows** — runs the chat and embedding models locally.
- **Node.js 20.19 or newer and npm** — builds and runs the React/Vite frontend.
  npm is included with Node.js.
- **Chrome or Edge** — recommended if you want to use the browser voice-input
  and voice-output features.

After installing them, open a new PowerShell window and verify the commands:

```powershell
git --version
py -3.12 --version
docker --version
docker compose version
ollama --version
node --version
npm --version
```

Each command should print a version. If one is not recognized, restart the
terminal and check that the program was added to `PATH`.

## 2. One-time project setup

Run these commands from the repository root (the folder containing
`requirements.txt`, `compose.yaml`, and `run.ps1`).

### Create the Python environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

What this does:

1. `.venv` creates an isolated Python installation for this project.
2. `Activate.ps1` makes the terminal use that environment.
3. pip is updated and then installs FastAPI, Uvicorn, PostgreSQL support,
   LangGraph, PDF processing, and the other backend dependencies.

If PowerShell blocks `Activate.ps1`, run this once in the current terminal and
then activate it again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Configure local environment variables

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace `change-this-local-password` with a local database
password. The other defaults are ready for local development. This file tells
the backend how to reach PostgreSQL and Ollama, which models to use, where to
store documents, and which safety options are enabled. Do not commit `.env`.

### Download the Ollama models

Make sure Ollama is running, then execute:

```powershell
ollama pull qwen3:8b
ollama pull embeddinggemma
```

- `qwen3:8b` generates chat responses and selects assistant tools.
- `embeddinggemma` converts uploaded document text into vectors so the
  assistant can search household documents.

Optional smoke test after the Python environment is active:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) "src"
python -m app.llm
```

This sends one request to Ollama and confirms that the backend can use the
configured chat model.

### Install frontend packages

```powershell
Set-Location ui
npm install
Copy-Item .env.example .env -ErrorAction SilentlyContinue
Set-Location ..
```

`npm install` installs React, Vite, TypeScript, and the frontend test/build
tools. `ui/.env` sets `VITE_API_BASE_URL=http://127.0.0.1:9000`, which tells the
browser where to find the backend.

## 3. Start the complete application

Keep each long-running command open in its own PowerShell terminal.

### Terminal 1: PostgreSQL

From the repository root:

```powershell
docker compose up -d db
docker compose ps
```

This starts PostgreSQL in Docker and exposes it only on
`127.0.0.1:5432`. Wait until `docker compose ps` reports the database as
`healthy`. Database data is kept in a Docker volume between restarts. The
initial schema is created automatically the first time the volume is used;
later application migrations run when the backend or worker starts.

### Terminal 2: FastAPI backend

From the repository root:

```powershell
.\run.ps1
```

This uses `.venv`, adds `src` to Python's import path, and runs FastAPI with
automatic reload on port `9000`.

Check it at:

- API health: <http://127.0.0.1:9000/health>
- Interactive API documentation: <http://127.0.0.1:9000/docs>

### Terminal 3: document worker

From the repository root:

```powershell
.\run-worker.ps1
```

The worker watches PostgreSQL for document jobs. It extracts text from
uploaded `.txt`, `.md`, and text-based `.pdf` files, asks `embeddinggemma` for
embeddings, stores searchable chunks, and handles document deletion jobs. The
normal chat UI can run without it, but uploaded documents will not finish
indexing unless the worker is running.

### Terminal 4: React frontend

From the repository root:

```powershell
Set-Location ui
npm run dev
```

This starts the Vite development server, normally at
<http://localhost:5173>. Open that address in Chrome or Edge. Vite reloads the
page as frontend source files change.

## 4. Optional sample data

In another PowerShell terminal at the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = Join-Path (Get-Location) "src"
python -m app.seed_data
```

This adds example rooms, devices, and inventory records when they do not
already exist. It does not overwrite existing values.

## 5. Normal startup after the one-time setup

On later runs, you only need to:

1. Start Docker Desktop and Ollama.
2. Run `docker compose up -d db` from the repository root.
3. Run `.\run.ps1` in a second terminal.
4. Run `.\run-worker.ps1` in a third terminal.
5. Run `npm run dev` from `ui` in a fourth terminal.
6. Open <http://localhost:5173>.

## 6. Stop the project

- Press `Ctrl+C` in the backend, worker, and frontend terminals.
- Stop PostgreSQL without deleting its data:

  ```powershell
  docker compose down
  ```

Do not add `-v` unless you intentionally want to delete the local PostgreSQL
volume and all of its project data.

## Quick troubleshooting

- **Backend health returns 503:** confirm Docker Desktop is running and the
  `db` service is `healthy` with `docker compose ps`.
- **Ollama/model error:** open Ollama and confirm both models appear in
  `ollama list`.
- **`run.ps1` cannot find Python:** complete the `.venv` setup from section 2.
- **Documents remain queued:** keep `run-worker.ps1` running and check its
  terminal for errors.
- **Frontend cannot reach the API:** confirm the backend is running on port
  `9000` and `ui/.env` contains
  `VITE_API_BASE_URL=http://127.0.0.1:9000`.
- **Port already in use:** stop the process already using ports `5432`, `9000`,
  or `5173`. The backend can use another port with `.\run.ps1 -Port 9001`,
  but `ui/.env` must then use the same port.
