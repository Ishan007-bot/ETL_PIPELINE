from fastapi import FastAPI
from .ingest import router as ingest_router
from .upload import router as upload_router
from .schema_api import router as schema_router
from .migrate_api import router as migrate_router
from .query_api import router as query_router

app = FastAPI(title="Chrysalis Dynamic ETL API", version="0.2")

# Keep old /ingest for backward compatibility
app.include_router(ingest_router, prefix="", tags=["ingest"])

# New /upload endpoint for file uploads
app.include_router(upload_router, prefix="", tags=["upload"])

# Schema endpoints
app.include_router(schema_router, prefix="", tags=["schema"])

# Migration endpoint
app.include_router(migrate_router, prefix="", tags=["migration"])

# Query endpoints
app.include_router(query_router, prefix="", tags=["query"])

@app.get("/health")
async def health():
    return {"status":"ok"}

