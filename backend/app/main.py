from fastapi import FastAPI
from .ingest import router as ingest_router

app = FastAPI(title="Chrysalis Ingest API", version="0.1")

app.include_router(ingest_router, prefix="", tags=["ingest"])

@app.get("/health")
async def health():
    return {"status":"ok"}

