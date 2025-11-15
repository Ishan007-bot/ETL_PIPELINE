# Chrysalis - Dynamic ETL with Schema Versioning

A dynamic ETL system that automatically detects schema drift and creates versioned schemas.

## Project Structure

```
chrysalis/
├─ backend/
│  ├─ app/
│  ├─ requirements.txt
│  └─ demo.sh
├─ demo/
│  └─ streamlit_app.py
├─ infra/
│  └─ docker-compose.yml
├─ fixtures/
├─ tests/
└─ README.md
```

## Setup

1. Create virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r backend/requirements.txt
```

## Running the Application

### Using Docker Compose (Recommended)

1. Start all services:
```bash
docker compose -f infra/docker-compose.yml up --build
```

This will start:
- Redis on port 6379
- MongoDB on port 27017
- FastAPI on port 8000
- Worker (background processing)
- Streamlit on port 8501

2. Run the demo script:
```bash
cd backend
bash demo.sh
# Or on Windows with Git Bash: bash demo.sh
```

3. View results:
- Streamlit UI: http://localhost:8501
- API docs: http://localhost:8000/docs

### Running Locally (Without Docker)

1. Start Redis and MongoDB locally
2. Set environment variables:
```bash
export REDIS_URL=redis://localhost:6379/0
export MONGO_URL=mongodb://localhost:27017
```

3. Start API:
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

4. Start worker (in separate terminal):
```bash
cd backend
python app/worker.py
```

5. Start Streamlit (in separate terminal):
```bash
streamlit run demo/streamlit_app.py
```

## Testing

Run tests:
```bash
cd backend
pytest ../tests/ -v
```

## Acceptance Checklist

✅ **Infrastructure**
- [x] `docker compose -f infra/docker-compose.yml up` starts Redis, Mongo, API, worker, and Streamlit
- [x] Redis & Mongo show healthy status in logs

✅ **API**
- [x] `POST /ingest` returns 202 and job lands in Redis queue
- [x] Health endpoint `/health` returns status

✅ **Worker**
- [x] Worker processes job and writes schema entry to `schema_registry`
- [x] Inserted docs appear in `raw_data` with `_schema_version`, `_ingest_job_id`, `_ingest_ts`

✅ **Schema Versioning**
- [x] Schema inference works with GenSON
- [x] Schema diff detects added/removed/changed fields
- [x] Drift decision creates new versions based on thresholds
- [x] Version manager stores schemas in MongoDB `schema_registry` collection

✅ **UI**
- [x] Streamlit shows schema diffs and sample docs
- [x] Streamlit displays ingested documents
- [x] DLQ entries visible in Streamlit sidebar

✅ **DLQ**
- [x] DLQ receives intentionally sent malformed docs
- [x] Failed jobs are stored in Redis DLQ queue

✅ **Demo**
- [x] `backend/demo.sh` executes fixtures A/B/C
- [x] Demo demonstrates version increments

✅ **Tests**
- [x] `pytest` passes basic schema diff tests

