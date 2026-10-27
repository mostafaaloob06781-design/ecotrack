# EcoTrack — منصة ذكية لتقليل هدر الطعام

Cloud Computing course project. FastAPI + SQLite + scikit-learn, deployed on Render.

## Run locally
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload      # http://127.0.0.1:8000
python -m tests.test_app           # end-to-end tests
```

## Demo accounts (password for all: `Demo1234`)
| Role | Email |
|---|---|
| Restaurant | restaurant@ecotrack.test |
| Restaurant | oasis@ecotrack.test |
| Beneficiary | student@ecotrack.test |

## AI part
```bash
python -m ai.generate_data   # synthetic dataset -> data/surplus.csv (800 rows)
python -m ai.train_model     # trains Linear Regression vs Random Forest, prints MAE and R2
```
- `POST /api/ai/predict-surplus` — Random Forest surplus forecast (restaurant only)
- `POST /api/ai/suggest-discount` — rule-based discount suggestion (restaurant only)
- `GET  /api/ai/forecast-chart` — actual vs predicted data for the stats chart

## Security (Cyber part)
bcrypt password hashing · signed session cookies (HttpOnly, SameSite, Secure in prod) · role-based access control + ownership checks ·
CSRF tokens on every POST · login/register/AI rate limiting · parameterized SQL (no SQL injection) · Jinja2 auto-escaping (no XSS) ·
CSP, X-Frame-Options, HSTS and other security headers · input validation (Pydantic + server-side checks) · HTTPS via the cloud provider.

## Deploy on Render
1. Push this folder to a GitHub repo.
2. Render dashboard -> New -> Blueprint (or Web Service) -> select the repo. `render.yaml` sets everything up.
3. Open the URL Render gives you. Health check: `/health`.

Note: on the free plan the SQLite file resets on redeploy/restart; demo data is re-seeded automatically (`SEED_DEMO=1`).
