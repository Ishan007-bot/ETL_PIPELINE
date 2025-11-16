# Chrysalis - Dynamic ETL Pipeline with Intelligent Schema Evolution

A production-ready dynamic ETL system that automatically ingests unstructured data, infers schemas, detects schema drift, and creates versioned schemas. Handles mixed-format data (JSON, HTML, CSV, key-value pairs) with intelligent extraction prioritization.

## 🎯 Key Features

- **Zero-Schema Ingestion**: Store data without knowing structure upfront
- **Intelligent Multi-Format Extraction**: JSON, HTML, CSV, key-value pairs, raw text
- **Smart Extraction Prioritization**: Detects structured data and prioritizes it over noise
- **Automatic Schema Inference**: Generates JSON schemas using GenSON
- **Schema Evolution Tracking**: Automatic drift detection and versioning
- **Multi-Database Support**: MongoDB, PostgreSQL, Neo4j
- **Natural Language Querying**: LLM-powered query translation
- **Production-Ready**: Error handling, logging, security, DLQ

## 🏗️ Architecture

### System Components

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /upload
       ▼
┌─────────────────┐
│  FastAPI API    │  Port 8000
│  - File Upload  │
│  - Schema API   │
│  - Query API    │
└──────┬──────────┘
       │ Queue Job
       ▼
┌─────────────────┐
│  Redis Queue    │  Port 6379
│  - Job Queue    │
│  - DLQ          │
└──────┬──────────┘
       │ Worker Consumes
       ▼
┌─────────────────┐
│  Worker Process │
│  - Parse        │
│  - Extract      │
│  - Clean        │
│  - Infer Schema │
│  - Version      │
└──────┬──────────┘
       │ Store Data & Schema
       ▼
┌─────────────────────────┐
│   MongoDB (Primary)      │  Port 27017
│   PostgreSQL             │  Port 5432
│   Neo4j                  │  Ports 7474, 7687
└─────────────────────────┘
       │
       ▼
┌─────────────────┐
│  Streamlit UI   │  Port 8501
│  - Schema View  │
│  - Data View    │
│  - DLQ Monitor  │
└─────────────────┘
```

### Component Responsibilities

- **FastAPI API**: Handles file uploads, schema retrieval, query execution
- **Redis**: Job queue for async processing, DLQ for failed jobs
- **Worker**: Background ETL processing (parsing, extraction, cleaning, schema inference)
- **MongoDB**: Primary document store (flexible, schema-less)
- **PostgreSQL**: Relational store (SQL queries, ACID compliance)
- **Neo4j**: Graph database (relationships, graph queries)
- **Streamlit**: Demo UI for visualization and monitoring

## 🚀 Quick Start

### Using Docker Compose

```bash
cd infra
docker compose up -d --build
```

**Services**:
- FastAPI: http://localhost:8000
- Streamlit UI: http://localhost:8501
- API Docs: http://localhost:8000/docs

**Test Upload**:
```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@test_data.txt" \
  -F "source_id=test_001"
```

## 📡 API Endpoints

### File Upload
- **`POST /upload`** - Upload .txt/.pdf/.md files
  - Parameters: `file`, `source_id`, `metadata` (optional)
  - Returns: `source_id`, `file_id`, `parsed_fragments_summary`

### Schema Management
- **`GET /schema?source_id=<id>`** - Get current schema
- **`GET /schema/history?source_id=<id>`** - Get schema version history

### Query Execution
- **`POST /query`** - Execute natural language or direct database queries
  - Parameters: `source_id`, `nl_query` (optional), `db_query` (optional), `db_type`
- **`GET /records?query_id=<id>`** - Get async query results

### Health
- **`GET /health`** - Health check

## 🔄 Data Flow

1. Upload file → Parse → Extract (JSON/HTML/CSV/KV)
2. Queue job → Worker processes
3. Clean data → Infer schema → Detect drift
4. Store in MongoDB/PostgreSQL/Neo4j
5. Query with natural language or direct queries

## 🧠 Intelligent Features

- **Product-Like JSON Detection**: Automatically prioritizes structured JSON over CSV/HTML noise
- **Type Preservation**: Maintains nested objects and arrays (no flattening)
- **Noise Filtering**: Removes single-letter fields, malformed names, wrapper fields
- **JSON Comment Handling**: Parses JSON with comments and trailing commas
- **Error Resilience**: Never crashes, DLQ for failed jobs, always returns valid responses

## 🛠️ Technology Stack

- **Backend**: FastAPI, GenSON, BeautifulSoup4, Pandas, PyPDF2, OpenAI API
- **Databases**: MongoDB, PostgreSQL, Neo4j
- **Infrastructure**: Redis, Docker Compose, Streamlit

## 📊 Example Schema Response

```json
{
  "schema_id": "schema_v3",
  "version": 3,
  "compatible_dbs": ["postgresql", "mongodb", "neo4j"],
  "fields": [
    {
      "name": "product_id",
      "type": ["integer", "string"],
      "example": 9001
    },
    {
      "name": "tags",
      "type": "array",
      "example": ["sensor", "wireless"]
    }
  ],
  "primary_key_candidates": ["product_id"]
}
```

## 📈 Schema Evolution

The system automatically detects schema changes:
- **v1**: `product_id` (integer), `name` (string), `price` (number)
- **v2**: Added `status` field → New version created
- **v3**: `price` changes to `["number", "string"]` → New version with type union

View history: `GET /schema/history?source_id=<id>`

## 🔒 Security

- File upload validation (size, type, content)
- SQL injection prevention
- Input sanitization
- Structured security event logging

## 📚 Documentation

- **Setup Guide**: `SETUP_GUIDE.md`
- **Interview Guide**: `INTERVIEW_GUIDE.md` (complete system explanation)
- **API Docs**: http://localhost:8000/docs

## 🧪 Testing

```bash
# Upload test file
curl -X POST "http://localhost:8000/upload" \
  -F "file=@test_data.txt" \
  -F "source_id=test_001"

# Get schema
curl "http://localhost:8000/schema?source_id=test_001"
```

## 🎯 Use Cases

- Web scraping with unknown structure
- API integration with changing schemas
- Data lakes (store first, infer schema later)
- ETL pipelines with automatic schema evolution
- Multi-source data aggregation

---

**Built for dynamic ETL pipeline evaluation** 🚀
