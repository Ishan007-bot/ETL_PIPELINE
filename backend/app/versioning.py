from pymongo import MongoClient
import os
from datetime import datetime
import pymongo

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
client = MongoClient(MONGO_URL)
db = client["chrysalis"]
SCHEMA_COLLECTION = db["schema_registry"]

class VersioningManager:
    def __init__(self):
        SCHEMA_COLLECTION.create_index([("version", pymongo.DESCENDING)], unique=False)
        SCHEMA_COLLECTION.create_index([("source_id", pymongo.ASCENDING), ("version", pymongo.DESCENDING)], unique=False)
    
    def get_latest(self, source_id=None):
        if source_id:
            doc = SCHEMA_COLLECTION.find_one(
                {"source_id": source_id},
                sort=[("version", -1)]
            )
        else:
            doc = SCHEMA_COLLECTION.find_one(sort=[("version", -1)])
        return doc
    
    def create_new_version(self, schema, diff, cause_batch_id, sample_docs, field_stats=None, source_id=None, enhanced_schema=None, db_compatibility=None):
        latest = self.get_latest(source_id=source_id)
        if latest:
            new_version = latest["version"] + 1
        else:
            # Check if there are any schemas for this source_id
            existing = SCHEMA_COLLECTION.find_one({"source_id": source_id}, sort=[("version", -1)])
            new_version = (existing["version"] + 1) if existing else 1
        
        metadata = {
            "version": new_version,
            "schema": schema,
            "enhanced_schema": enhanced_schema or schema,
            "schema_id": f"schema_v{new_version}",
            "source_id": source_id,
            "diff": {
                "added": getattr(diff, "added", {}),
                "removed": getattr(diff, "removed", {}),
                "changed": getattr(diff, "changed", {})
            },
            "created_at": datetime.utcnow().isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "cause_batch_id": cause_batch_id,
            "sample_docs": sample_docs,
            "field_stats": field_stats or {},
            "db_compatibility": db_compatibility or {}
        }
        
        SCHEMA_COLLECTION.insert_one(metadata)
        return metadata
