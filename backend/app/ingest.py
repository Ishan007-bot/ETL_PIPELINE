from fastapi import APIRouter, HTTPException
from fastapi import Body
import uuid
import orjson
import redis
import os
from datetime import datetime

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=False)

QUEUE_NAME = "chrysalis:ingest:queue"

@router.post("/ingest")
async def ingest(batch: dict = Body(...)):
    if "documents" not in batch:
        raise HTTPException(400, detail="Missing 'documents' array in request body")
    
    job_id = str(uuid.uuid4())
    
    payload = {
        "job_id": job_id,
        "source": batch.get("source", "unknown"),
        "received_at": datetime.utcnow().isoformat(),
        "documents": batch["documents"]
    }
    
    msg = orjson.dumps(payload)
    r.lpush(QUEUE_NAME, msg)
    
    return {"job_id": job_id, "status": "accepted"}

