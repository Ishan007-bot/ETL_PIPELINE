import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
import orjson
import time
from app.schema_infer import infer_schema_from_sample
from app.schema_diff import compute_schema_diff, DriftDecision
from app.versioning import VersioningManager
from app.storage import StorageManager
from app.dlq import send_to_dlq
from app.cleaning import clean_documents
from app.schema_metadata import enhance_schema_with_metadata, generate_db_compatibility_metadata
from app.migration import generate_migration_plan
from app.multidb import MultiDBManager
from app.app_logging import setup_logging, get_logger, log_schema_generation, log_schema_evolution, log_error
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = "chrysalis:ingest:queue"

r = redis.from_url(REDIS_URL, decode_responses=False)

version_manager = VersioningManager()
storage = StorageManager()
multidb = MultiDBManager()

# Setup logging
logger = setup_logging(os.getenv("LOG_LEVEL", "INFO"))

BLPOP_TIMEOUT = 5  # seconds

def process_job(raw_msg: bytes):
    job_id = None
    source_id = None
    try:
        job = orjson.loads(raw_msg)
    except Exception as e:
        log_error(logger, "job_parse_error", f"Failed to parse job: {str(e)}")
        send_to_dlq(raw_msg, reason="invalid_job_payload")
        return
    
    try:
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
            # Instead of failing, create a minimal document from raw content
            log_error(logger, "empty_documents", f"Job {job_id} has no documents, creating fallback", {"job_id": job_id})
            # Try to extract from parsed_file or extraction_result
            if "parsed_file" in job:
                raw_content = job.get("parsed_file", {}).get("content", "")
                if raw_content:
                    docs = [{"_raw_content": str(raw_content)[:1000]}]
                else:
                    send_to_dlq(job, reason="empty_documents")
                    return
            else:
                send_to_dlq(job, reason="empty_documents")
                return
        
        logger.info(f"Processing job {job_id}, {len(docs)} docs", extra={
            "extra_fields": {
                "event_type": "job_processing",
                "job_id": job_id,
                "source_id": source_id,
                "document_count": len(docs)
            }
        })
        
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
        
        logger.info(f"Cleaned documents: {len(cleaned_docs)} (removed {quality_metrics.get('duplicates_removed', 0)} duplicates)", extra={
            "extra_fields": {
                "event_type": "data_cleaning",
                "job_id": job_id,
                "cleaned_count": len(cleaned_docs),
                "duplicates_removed": quality_metrics.get('duplicates_removed', 0),
                "quality_score": quality_metrics.get('quality_score', 0.0)
            }
        })
        
        # sampling & preprocessing (use cleaned documents)
        sample = cleaned_docs[:200]
        candidate_schema, field_stats = infer_schema_from_sample(sample, return_stats=True)
        
        # Enhance schema with metadata
        enhanced_schema = enhance_schema_with_metadata(
            candidate_schema,
            field_stats,
            sample[:10],  # Use more samples for examples
            source_offsets=None  # TODO: track source offsets from extraction
        )
        
        # Generate DB compatibility metadata
        db_compatibility = generate_db_compatibility_metadata(candidate_schema)
        compatible_dbs_list = db_compatibility.get('compatible_dbs', [])
        logger.info(f"Schema compatible with: {', '.join(compatible_dbs_list)}", extra={
            "extra_fields": {
                "event_type": "schema_metadata",
                "source_id": source_id,
                "compatible_dbs": compatible_dbs_list
            }
        })
        
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
                logger.warning(f"Migration has data loss risk. Warnings: {len(migration_plan.get('warnings', []))}", extra={
                    "extra_fields": {
                        "event_type": "migration_warning",
                        "source_id": source_id,
                        "warnings_count": len(migration_plan.get('warnings', []))
                    }
                })
            
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
            
            log_schema_generation(
                logger,
                source_id,
                schema_id,
                version,
                len(candidate_schema.get("properties", {}))
            )
            
            if latest_schema_meta:
                log_schema_evolution(
                    logger,
                    source_id,
                    latest_schema_meta.get("version", 1),
                    version,
                    diff.__dict__ if hasattr(diff, "__dict__") else {}
                )
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
    except Exception as e:
        import traceback
        error_msg = f"Error processing job {job_id}: {str(e)}"
        log_error(logger, "job_processing_error", error_msg, {
            "job_id": job_id,
            "source_id": source_id,
            "traceback": traceback.format_exc()
        })
        print(f"Worker error in process_job: {e}")
        traceback.print_exc()
        send_to_dlq(raw_msg, reason=f"processing_error: {str(e)}")

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

