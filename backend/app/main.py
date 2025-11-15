from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .ingest import router as ingest_router
from .upload import router as upload_router
from .schema_api import router as schema_router
from .migrate_api import router as migrate_router
from .query_api import router as query_router
from .logging import setup_logging, get_logger, log_error
import traceback

# Setup logging
logger = setup_logging()

app = FastAPI(title="Chrysalis Dynamic ETL API", version="0.3")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Health check endpoint."""
    return {"status": "ok", "service": "chrysalis-etl"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    log_error(
        logger,
        "unhandled_exception",
        f"Unhandled exception: {str(exc)}",
        {
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc()
        }
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "error_type": type(exc).__name__
        }
    )

