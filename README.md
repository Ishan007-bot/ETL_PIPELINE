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
- PostgreSQL on port 5432
- Neo4j on ports 7474 (HTTP) and 7687 (Bolt)
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

## API Endpoints

### File Upload
- `POST /upload` - Upload .txt/.pdf/.md files with multipart/form-data
  - Parameters: `file`, `source_id`, `metadata` (optional)
  - Returns: `source_id`, `file_id`, `schema_id`, `parsed_fragments_summary`

### Schema Management
- `GET /schema?source_id=<id>` - Get current schema for source
- `GET /schema/history?source_id=<id>` - Get schema version history with diffs

### Query Execution
- `POST /query` - Execute natural language or direct database queries
  - Parameters: `source_id`, `nl_query` (optional), `db_query` (optional), `db_type`, `async_mode`
- `GET /records?source_id=<id>&query_id=<id>` - Get query results

### Migration
- `POST /migrate?source_id=<id>&target_version=<v>&dry_run=true` - Trigger schema migration

### Health & Legacy
- `GET /health` - Health check
- `POST /ingest` - Legacy JSON document ingestion (backward compatible)

## Acceptance Checklist

✅ **Infrastructure**
- [x] `docker compose -f infra/docker-compose.yml up` starts all services (Redis, Mongo, PostgreSQL, Neo4j, API, worker, Streamlit)
- [x] All services show healthy status in logs

✅ **File Upload & Parsing**
- [x] `POST /upload` accepts .txt, .pdf, .md files
- [x] Multi-format extraction (JSON, HTML, CSV, key-value, raw text)
- [x] Returns `parsed_fragments_summary` with fragment counts

✅ **Data Cleaning**
- [x] Field name normalization (snake_case)
- [x] Type detection and coercion
- [x] Date format parsing
- [x] Duplicate removal
- [x] Data quality scoring

✅ **Schema Generation**
- [x] Automatic schema inference with GenSON
- [x] Enhanced metadata (confidence scores, primary keys, examples)
- [x] Multi-DB compatibility (PostgreSQL, MongoDB, Neo4j)
- [x] Schema versioning with diffs

✅ **Schema Endpoints**
- [x] `GET /schema` returns canonical schema format
- [x] `GET /schema/history` returns version history with diffs

✅ **Migration & Backward Compatibility**
- [x] Migration plan generation
- [x] Data transformation rules
- [x] Backward compatibility checking
- [x] Query routing to schema versions

✅ **Query Execution**
- [x] `POST /query` with natural language support (LLM integration)
- [x] `POST /query` with direct database queries
- [x] `GET /records` for async query results
- [x] Multi-DB query execution (MongoDB, PostgreSQL, Neo4j)

✅ **Multi-DB Support**
- [x] PostgreSQL connection and operations
- [x] Neo4j connection and operations
- [x] Schema creation in all compatible databases
- [x] Data insertion into multiple databases

✅ **Security & Logging**
- [x] Structured JSON logging
- [x] File upload validation
- [x] SQL injection prevention
- [x] Input sanitization
- [x] Security event logging
- [x] Global exception handling

✅ **UI**
- [x] Streamlit shows schema diffs and sample docs
- [x] Streamlit displays ingested documents
- [x] DLQ entries visible in Streamlit sidebar

✅ **DLQ**
- [x] DLQ receives intentionally sent malformed docs
- [x] Failed jobs are stored in Redis DLQ queue

✅ **Tests**
- [x] `pytest` passes basic schema diff tests

