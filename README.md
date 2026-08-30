# RoleLens

RoleLens is an evidence-backed decision workspace that shows how human scenario revisions change decision posture across five governed role views.

## Quickstart

Prerequisites:

- Python 3.13 (tested with Python 3.13.5)
- Node.js 20.19+ or 22.12+

Start the backend from the repository root:

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.product_api:app --reload --port 8000
```

In a second terminal, start the frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. The Vite development server proxies `/api` requests to `http://127.0.0.1:8000`.

For explicit live IBM Granite role-brief generation, configure these environment variables before starting the backend:

```text
WATSONX_URL
WATSONX_APIKEY
WATSONX_PROJECT_ID
WATSONX_MODEL_ID
```

`WATSONX_MODEL_ID` is optional and defaults to `ibm/granite-4-h-small`. Credentials must not be committed.

## Demo Data

The committed public demo assets and their third-party provenance are documented in [sample_data/public/README.md](sample_data/public/README.md).

## Verification

```bash
pytest
cd frontend
npm run test -- --run
npm run build
```
