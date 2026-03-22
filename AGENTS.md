# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Montreal Environmental Purity Score (MEPS) — a full-stack web app with a React 18 frontend and a FastAPI backend. The questionnaire flow computes an environmental purity score; an optional Computer Use inspector panel uses OpenAI + Playwright (requires `OPENAI_API_KEY`).

### Services

| Service | Port | Start command | Working directory |
|---------|------|---------------|-------------------|
| FastAPI backend | 8000 | `source /workspace/.venv/bin/activate && uvicorn main:app --reload` | `FastAPI/` |
| React frontend | 3000 | `BROWSER=none npm start` | `React/questionnaire-app/` |

The frontend calls the backend at `http://localhost:8000` (hardcoded in `React/questionnaire-app/src/api.js`).

### Lint / Test / Build

- **Python lint**: `python3 -m py_compile FastAPI/main.py` (repeat for each `.py` file). No dedicated Python linter config exists.
- **React lint**: `npx eslint src/` from `React/questionnaire-app/`. Two pre-existing `import/first` warnings in `App.test.js` are expected (jest.mock hoisting pattern).
- **React tests**: `CI=true npm test -- --watchAll=false` from `React/questionnaire-app/`.
- **React build**: `npm run build` from `React/questionnaire-app/`.
- **Backend health check**: `curl http://localhost:8000/health` returns `{"status":"ok"}`.

### Non-obvious notes

- There is **no `requirements.txt`** in the repo. Python deps must be installed manually: `pip install fastapi sqlalchemy uvicorn matplotlib numpy scipy pydantic openai`.
- The checked-in `env/` directory is a macOS-originated virtualenv and is **not usable** on Linux. A fresh `.venv` must be created with `python3 -m venv .venv`.
- `python3.12-venv` system package is required on Ubuntu to create virtualenvs (`sudo apt-get install -y python3.12-venv`).
- SQLite database (`FastAPI/answer.db`) is auto-created by SQLAlchemy on first run — no migration step needed.
- The Computer Use flow (Playwright + OpenAI) is **optional**. The core questionnaire works without `OPENAI_API_KEY`.
- Static files (generated graphs, screenshots) are served from `FastAPI/static/` and that directory is auto-created at startup.
