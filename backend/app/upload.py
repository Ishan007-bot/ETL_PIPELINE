"""
File upload endpoint for .txt, .pdf, .md files.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import uuid
import orjson
import redis
import os
from datetime import datetime
from .parsers import parse_file
from .extractors import extract_all_fragments

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=False)

QUEUE_NAME = "chrysalis:ingest:queue"

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    source_id: str = Form(...),
    metadata: str = Form(None)
):
    """
    Upload a file (.txt, .pdf, .md) for processing.
    
    Expected multipart/form-data:
    - file: binary file
    - source_id: string identifier for the source
    - metadata: optional JSON string with additional metadata
    """
    # Validate file type
    allowed_extensions = ['.txt', '.pdf', '.md']
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Read file content
    try:
        file_content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
    
    # Validate file size (e.g., max 100MB)
    max_size = 100 * 1024 * 1024  # 100MB
    if len(file_content) > max_size:
        raise HTTPException(status_code=400, detail="File too large. Maximum size: 100MB")
    
    # Parse file
    try:
        parsed_file = parse_file(file_content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
    
    # Extract fragments from content
    try:
        extraction_result = extract_all_fragments(parsed_file["content"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract fragments: {str(e)}")
    
    # Generate IDs
    file_id = f"file_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
    job_id = str(uuid.uuid4())
    
    # Parse metadata if provided
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = orjson.loads(metadata)
        except:
            pass
    
    # Prepare job payload
    payload = {
        "job_id": job_id,
        "source_id": source_id,
        "file_id": file_id,
        "file_type": parsed_file["file_type"],
        "filename": file.filename,
        "received_at": datetime.utcnow().isoformat(),
        "metadata": parsed_metadata,
        "parsed_file": parsed_file,
        "extraction_result": extraction_result,
        "documents": extraction_result["documents"]
    }
    
    # Push to queue
    try:
        msg = orjson.dumps(payload)
        r.lpush(QUEUE_NAME, msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {str(e)}")
    
    # Return response matching evaluation guide format
    return JSONResponse({
        "status": "ok",
        "source_id": source_id,
        "file_id": file_id,
        "schema_id": None,  # Will be set after processing
        "parsed_fragments_summary": extraction_result["parsed_fragments_summary"]
    })

