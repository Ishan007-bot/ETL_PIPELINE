import redis
import os
import orjson
import time
from .schema_infer import infer_schema_from_sample
from .schema_diff import compute_schema_diff, DriftDecision
from .versioning import VersioningManager
from .storage import StorageManager
from .dlq import send_to_dlq
from .cleaning import clean_documents
from .schema_metadata import enhance_schema_with_metadata, generate_db_compatibility_metadata
from .migration import generate_migration_plan
from .multidb import MultiDBManager
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = "chrysalis:ingest:queue"

r = redis.from_url(REDIS_URL, decode_responses=False)

version_manager = VersioningManager()
storage = StorageManager()
multidb = MultiDBManager()

BLPOP_TIMEOUT = 5  # seconds

def process_job(raw_msg: bytes):
    try:
        job = orjson.loads(raw_msg)
    except Exception as e:
        print("Failed to parse job:", e)
        send_to_dlq(raw_msg, reason="invalid_job_payload")
        return
    
    job_id = job.get("job_id")
    
    # Handle both old format (documents) and new format (from file upload)
    if "documents" in job:
        # Old format: direct documents
        docs = job.get("documents", [])
        source_id = job.get("source", "unknown")
    elif "extraction_result" in job:
        # New format: from file upload
        extraction_result = job.get("extraction_result", {})
        docs = extraction_result.get("documents", [])
        source_id = job.get("source_id", "unknown")
        job["source"] = source_id  # Normalize for processing
    else:
        print(f"Job {job_id} has no documents or extraction_result")
        send_to_dlq(job, reason="empty_documents")
        return
    
    if not isinstance(docs, list) or len(docs) == 0:
        print(f"Job {job_id} has no documents")
        send_to_dlq(job, reason="empty_documents")
        return
    
    print(f"[{datetime.utcnow().isoformat()}] Processing job {job_id}, {len(docs)} docs")
    
    # Data cleaning and canonicalization
    print(f"Cleaning {len(docs)} documents...")
    cleaning_result = clean_documents(
        docs,
        normalize_names=True,
        remove_duplicates_flag=True,
        key_fields=None  # Auto-detect duplicates
    )
    cleaned_docs = cleaning_result["cleaned_documents"]
    quality_metrics = cleaning_result["quality_metrics"]
    
    print(f"Cleaned documents: {len(cleaned_docs)} (removed {quality_metrics.get('duplicates_removed', 0)} duplicates)")
    print(f"Data quality score: {quality_metrics.get('quality_score', 0.0):.2f}")
    
    # sampling & preprocessing (use cleaned documents)
    sample = cleaned_docs[:200]
    candidate_schema, field_stats = infer_schema_from_sample(sample, return_stats=True)
    
    # Enhance schema with metadata
    print("Enhancing schema with metadata...")
    enhanced_schema = enhance_schema_with_metadata(
        candidate_schema,
        field_stats,
        sample[:10],  # Use more samples for examples
        source_offsets=None  # TODO: track source offsets from extraction
    )
    
    # Generate DB compatibility metadata
    db_compatibility = generate_db_compatibility_metadata(candidate_schema)
    print(f"Schema compatible with: {', '.join(db_compatibility.get('compatible_dbs', []))}")
    
    latest_schema_meta = version_manager.get_latest(source_id=source_id)
    
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
        # Generate migration plan
        old_schema = latest_schema_meta.get("schema") if latest_schema_meta else None
        migration_plan = generate_migration_plan(
            old_schema,
            candidate_schema,
            diff,
            field_stats
        )
        
        if migration_plan.get("data_loss_risk"):
            print(f"WARNING: Migration has data loss risk. Warnings: {len(migration_plan.get('warnings', []))}")
        
        new_meta = version_manager.create_new_version(
            candidate_schema,
            diff,
            job_id,
            sample[:5],
            field_stats,
            source_id=source_id,
            enhanced_schema=enhanced_schema,
            db_compatibility=db_compatibility
        )
        schema_for_load = new_meta["schema"]
        version = new_meta["version"]
        schema_id = new_meta.get("schema_id", f"schema_v{version}")
        
        # Store migration plan in schema metadata
        new_meta["migration_plan"] = migration_plan
        from pymongo import MongoClient
        import os
        MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
        client = MongoClient(MONGO_URL)
        db = client["chrysalis"]
        SCHEMA_COLLECTION = db["schema_registry"]
        SCHEMA_COLLECTION.update_one(
            {"schema_id": schema_id},
            {"$set": {"migration_plan": migration_plan}}
        )
        
        print("Created new schema version:", version, "schema_id:", schema_id)
    else:
        schema_for_load = latest_schema_meta["schema"] if latest_schema_meta else candidate_schema
        version = latest_schema_meta["version"] if latest_schema_meta else 1
        schema_id = latest_schema_meta.get("schema_id", f"schema_v{version}") if latest_schema_meta else "schema_v1"
    
    success_docs = []
    failed_docs = []
    
    # validation + attach meta (use cleaned documents)
    for doc in cleaned_docs:
        try:
            # perform required-field checks using field_stats if available
            doc["_schema_version"] = version
            doc["_schema_id"] = schema_id
            doc["_ingest_job_id"] = job_id
            doc["_ingest_ts"] = datetime.utcnow().isoformat()
            doc["_source_id"] = source_id
            doc["_quality_score"] = quality_metrics.get("quality_score", 0.0)
            success_docs.append(doc)
        except Exception as e:
            failed_docs.append({"doc": doc, "reason": str(e)})
    
    if success_docs:
        # Store in MongoDB (primary)
        storage.insert_many(success_docs)
        
        # Store in other compatible databases if configured
        compatible_dbs = db_compatibility.get("compatible_dbs", ["mongodb"])
        if len(compatible_dbs) > 1:  # More than just MongoDB
            print(f"Inserting to additional databases: {compatible_dbs}")
            multidb.insert_to_databases(success_docs, source_id, compatible_dbs)
    
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

