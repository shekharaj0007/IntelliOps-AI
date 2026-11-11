# IntelliOps AI

Local prototype for intelligent IT operations. It gives an enterprise-style console for a synthetic fleet: spot server anomalies, score near-term failure risk, and investigate incidents with a playbook RCA.

This is not a live deployment. There is no production URL. Metrics in the database and in `metrics.json` come from a synthetic generator and from models trained on that generator. Do not quote them as measured production results.

## What the demo contains

- Six services across `us-east-1`, `eu-west-1`, and `ap-south-1`.
- About three days of metrics at a five-minute step.
- Injected CPU spikes, error bursts, and latency cliffs so the detector has something obvious to find.
- An IsolationForest per service on rolling level, delta, and z-score features.
- A logistic regression failure-risk score from recent error rate and latency behavior.
- JWT login for one seeded operator. The password is stored as a PBKDF2 hash.
- Playbook RCA and TF-IDF search over incident text. No external language model is called.

The API marks this data with `"data_origin": "synthetic"`. The console shows the same label.

On an empty database the process trains inside the seed, writes `models/anomaly_bundle.joblib`, and rewrites `metrics.json` with the holdout scores it just computed. `metrics.json` is the record of that run. The `holdout` object is the evaluation. Other keys describe the full-history fit and are labeled as such.

SQLite is the default database (`data/intelliops.db`). Set `DATABASE_URL` if you want another SQLAlchemy URL. Postgres and Redis are not required. If `REDIS_URL` is set and the `redis` package or the server is missing, startup skips Redis and continues.

## Run on Windows

From the repo root, in PowerShell:

```powershell
cd "C:\Users\raj shekhar\Downloads\IntelliOps-AI"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The first boot against an empty database trains the models. Give it a short moment.

In a second terminal:

```powershell
cd "C:\Users\raj shekhar\Downloads\IntelliOps-AI\frontend"
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` and `/metrics` to http://127.0.0.1:8000.

Interactive API docs from FastAPI are at http://127.0.0.1:8000/docs while the backend is running.

## Demo login

- Email: `operator@intelliops.ai`
- Password: `operator123`

This account is inserted when the user table is empty. It is a local demo login only.

## API

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/auth/login` | open |
| GET | `/api/health` | open |
| GET | `/metrics` | open |
| GET | `/api/services` | JWT |
| GET | `/api/services/{id}` | JWT |
| GET | `/api/anomalies` | JWT |
| POST | `/api/anomalies/{id}/ack` | JWT |
| GET | `/api/incidents` | JWT |
| POST | `/api/incidents` | JWT |
| POST | `/api/incidents/{id}/rca` | JWT |
| GET | `/api/incidents/similar?q=` | JWT |
| GET | `/api/overview` | JWT |

`GET /metrics` is Prometheus text for the process request count and the number of open anomalies.

Send the login token as `Authorization: Bearer <access_token>`.

## Test

`tests/test_anomaly_engine.py` builds a tiny calm series, appends a spiked window, fits IsolationForest on the calm portion, and checks that the spike is flagged.

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Optional environment

- `DATABASE_URL` — SQLAlchemy URL. Default is SQLite at `data/intelliops.db`.
- `JWT_SECRET` — signing secret. A development default is used when this is unset.
- `CORS_ORIGINS` — comma-separated list. Default is `http://localhost:5173`.
- `REDIS_URL` — optional. The app boots without Redis.
