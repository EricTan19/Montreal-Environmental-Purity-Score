# Montreal Environmental Purity Score

This repo now contains two working flows:

1. A repaired questionnaire UI that submits structured data to FastAPI and renders the returned score, badge, and graph URLs cleanly.
2. A local OpenAI Computer Use inspector that can open the web app in a Playwright browser, execute model-requested actions, return screenshots, and pause for approval when the API signals safety checks.

## Stack

- React 18 (`React/questionnaire-app`)
- FastAPI (`FastAPI`)
- OpenAI Responses API with the `computer-use-preview` model and `computer_use_preview` tool
- Playwright for local browser execution

## Prerequisites

- Node.js
- Python 3.10+
- An `OPENAI_API_KEY` in the backend environment

## Backend Setup

From the repo root:

```powershell
python -m pip install fastapi sqlalchemy uvicorn matplotlib numpy scipy openai playwright
python -m playwright install chromium
cd FastAPI
uvicorn main:app --reload
```

The backend serves:

- `POST /submit_answers`
- `POST /computer-use/sessions`
- `GET /computer-use/sessions/{session_id}`
- `POST /computer-use/sessions/{session_id}/continue`
- `POST /computer-use/sessions/{session_id}/approval`

Generated graphs and browser screenshots are served from `/static/...`.

## Frontend Setup

In a second terminal:

```powershell
cd React/questionnaire-app
npm install
npm start
```

The local app runs on `http://localhost:3000` and the API is expected on `http://localhost:8000`.

## Computer Use Notes

- The browser harness is implemented in [computer_use.py](/C:/Users/eric.tan/Montreal-Environmental-Purity-Score/FastAPI/computer_use.py).
- The React control panel is in [App.js](/C:/Users/eric.tan/Montreal-Environmental-Purity-Score/React/questionnaire-app/src/App.js).
- Sessions default to a localhost allow-list and will fail if the page navigates outside the approved hosts.
- If the OpenAI response contains `pending_safety_checks`, the backend stops and the frontend shows explicit `Approve` and `Deny` actions before continuing.
- Each continue cycle has a step budget so the browser loop does not run indefinitely inside one request.

## Verification

The following checks were run during implementation:

- `python` `py_compile` on the FastAPI modules
- FastAPI `TestClient` smoke test for `/submit_answers`
- `npm run build`
- `npm test -- --watchAll=false`
- Playwright smoke test for screenshot capture
- Live Computer Use session against a local static page via `/computer-use/sessions`
