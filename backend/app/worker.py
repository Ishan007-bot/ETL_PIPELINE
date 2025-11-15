import redis
import os
import orjson
import time
from .schema_infer import infer_schema_from_sample
from .schema_diff import compute_schema_diff, DriftDecision
from .versioning import VersioningManager
from .storage import StorageManager
from .dlq import send_to_dlq
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = "chrysalis:ingest:queue"

r = redis.from_url(REDIS_URL, decode_responses=False)

version_manager = VersioningManager()
storage = StorageManager()

BLPOP_TIMEOUT = 5  # seconds

def process_job(raw_msg: bytes):
    try:
        job = orjson.loads(raw_msg)
    except Exception as e:
        print("Failed to parse job:", e)
        send_to_dlq(raw_msg, reason="invalid_job_payload")
        return
    
    job_id = job.get("job_id")
    docs = job.get("documents", [])
    
    if not isinstance(docs, list) or len(docs) == 0:
        print(f"Job {job_id} has no documents")
        send_to_dlq(job, reason="empty_documents")
        return
    
    print(f"[{datetime.utcnow().isoformat()}] Processing job {job_id}, {len(docs)} docs")
    
    # sampling & preprocessing
    sample = docs[:200]
    candidate_schema, field_stats = infer_schema_from_sample(sample, return_stats=True)
    
    latest_schema_meta = version_manager.get_latest()
    
    diff = compute_schema_diff(
        latest_schema_meta.get("schema") if latest_schema_meta else None,
        candidate_schema,
        field_stats,
        latest_schema_meta
    )
    
    decision = DriftDecision.evaluate(
        diff,
        sample,
        old_field_stats=(latest_schema_meta.get("field_stats") if latest_schema_meta else None)
    )
    
    if decision.create_new_version:
        new_meta = version_manager.create_new_version(
            candidate_schema,
            diff,
            job_id,
            sample[:5],
            field_stats
        )
        schema_for_load = new_meta["schema"]
        version = new_meta["version"]
        print("Created new schema version:", version)
    else:
        schema_for_load = latest_schema_meta["schema"] if latest_schema_meta else candidate_schema
        version = latest_schema_meta["version"] if latest_schema_meta else 1
    
    success_docs = []
    failed_docs = []
    
    # validation + attach meta
    for doc in docs:
        try:
            # perform required-field checks using field_stats if available
            doc["_schema_version"] = version
            doc["_ingest_job_id"] = job_id
            doc["_ingest_ts"] = datetime.utcnow().isoformat()
            success_docs.append(doc)
        except Exception as e:
            failed_docs.append({"doc": doc, "reason": str(e)})
    
    if success_docs:
        storage.insert_many(success_docs)
    
    if failed_docs:
        for d in failed_docs:
            send_to_dlq(d, reason="validation_failed")

def main_loop():
    print("Worker started, polling Redis...")
    while True:
        try:
            item = r.brpop(QUEUE_NAME, timeout=BLPOP_TIMEOUT)
            if item:
                _, payload = item
                process_job(payload)
            else:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Worker interrupted")
            break
        except Exception as e:
            print("Worker error:", e)
            time.sleep(1)

if __name__ == "__main__":
    main_loop()

