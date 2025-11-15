from fastapi import FastAPI
from .ingest import router as ingest_router
from .upload import router as upload_router

app = FastAPI(title="Chrysalis Dynamic ETL API", version="0.2")

# Keep old /ingest for backward compatibility
app.include_router(ingest_router, prefix="", tags=["ingest"])

# New /upload endpoint for file uploads
app.include_router(upload_router, prefix="", tags=["upload"])

@app.get("/health")
async def health():
    return {"status":"ok"}

