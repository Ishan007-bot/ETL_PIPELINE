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
    
    def get_latest(self):
        doc = SCHEMA_COLLECTION.find_one(sort=[("version", -1)])
        return doc
    
    def create_new_version(self, schema, diff, cause_batch_id, sample_docs, field_stats=None):
        latest = self.get_latest()
        new_version = 1 if not latest else latest["version"] + 1
        
        metadata = {
            "version": new_version,
            "schema": schema,
            "diff": {
                "added": getattr(diff, "added", {}),
                "removed": getattr(diff, "removed", {}),
                "changed": getattr(diff, "changed", {})
            },
            "created_at": datetime.utcnow().isoformat(),
            "cause_batch_id": cause_batch_id,
            "sample_docs": sample_docs,
            "field_stats": field_stats or {}
        }
        
        SCHEMA_COLLECTION.insert_one(metadata)
        return metadata
