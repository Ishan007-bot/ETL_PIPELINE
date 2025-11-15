"""
Schema API endpoints for retrieving schemas and schema history.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from .versioning import VersioningManager
from pymongo import MongoClient
import os

router = APIRouter()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
client = MongoClient(MONGO_URL)
db = client["chrysalis"]
SCHEMA_COLLECTION = db["schema_registry"]

version_manager = VersioningManager()

def format_schema_response(schema_doc: dict) -> dict:
    """
    Format schema document to match evaluation guide response format.
    """
    if not schema_doc:
        return None
    
    enhanced_schema = schema_doc.get("enhanced_schema", schema_doc.get("schema", {}))
    db_compatibility = schema_doc.get("db_compatibility", {})
    
    # Extract fields with metadata
    fields = []
    if "fields" in enhanced_schema:
        # Use enhanced fields if available
        for field in enhanced_schema["fields"]:
            fields.append({
                "name": field.get("name"),
                "path": field.get("path", f"$.{field.get('name')}"),
                "type": field.get("type", "string"),
                "nullable": field.get("nullable", True),
                "example": field.get("example"),
                "confidence": field.get("confidence", 0.0),
                "source_offsets": field.get("source_offsets", [])
            })
    else:
        # Fallback: extract from properties
        properties = enhanced_schema.get("properties", {})
        field_stats = schema_doc.get("field_stats", {})
        sample_docs = schema_doc.get("sample_docs", [])
        
        for field_name, field_schema in properties.items():
            # Get example from sample docs
            example = None
            for doc in sample_docs[:5]:
                if field_name in doc:
                    example = doc[field_name]
                    break
            
            # Get confidence from field_stats
            confidence = 0.0
            if field_name in field_stats:
                stats = field_stats[field_name]
                presence_pct = stats.get("present_pct", 0)
                type_counts = stats.get("type_counts", {})
                if type_counts:
                    total = sum(type_counts.values())
                    dominant_type_pct = max(type_counts.values()) / total if total > 0 else 0
                    confidence = presence_pct * dominant_type_pct
                else:
                    confidence = presence_pct
            
            fields.append({
                "name": field_name,
                "path": f"$.{field_name}",
                "type": field_schema.get("type", "string"),
                "nullable": field_schema.get("nullable", True),
                "example": example,
                "confidence": confidence,
                "source_offsets": []
            })
    
    # Get primary key candidates
    primary_key_candidates = enhanced_schema.get("primary_key_candidates", [])
    if not primary_key_candidates and "primary_key_candidates" in schema_doc:
        primary_key_candidates = schema_doc["primary_key_candidates"]
    
    # Build migration notes from diff
    migration_notes = []
    diff = schema_doc.get("diff", {})
    if diff:
        added = diff.get("added", {})
        removed = diff.get("removed", {})
        changed = diff.get("changed", {})
        
        if added:
            for field_name, field_info in added.items():
                migration_notes.append(f"Added field '{field_name}' as {field_info.get('new', {}).get('type', 'unknown')}")
        
        if removed:
            for field_name, field_info in removed.items():
                old_type = field_info.get("old", {}).get("type", "unknown")
                migration_notes.append(f"Removed field '{field_name}' (was {old_type})")
        
        if changed:
            for field_name, field_info in changed.items():
                old_type = field_info.get("old", {}).get("type", "unknown")
                new_type = field_info.get("new", {}).get("type", "unknown")
                migration_notes.append(f"Changed field '{field_name}' from {old_type} to {new_type}")
    
    response = {
        "schema_id": schema_doc.get("schema_id", f"schema_v{schema_doc.get('version', 1)}"),
        "generated_at": schema_doc.get("generated_at", schema_doc.get("created_at", "")),
        "compatible_dbs": db_compatibility.get("compatible_dbs", ["postgresql", "mongodb"]),
        "fields": fields,
        "primary_key_candidates": primary_key_candidates,
        "migration_notes": migration_notes if migration_notes else None
    }
    
    return response

@router.get("/schema")
async def get_schema(source_id: str = Query(..., description="Source identifier")):
    """
    Get current schema for a source_id.
    
    Returns schema metadata in canonical format matching evaluation guide.
    """
    # Find latest schema for this source_id
    schema_doc = SCHEMA_COLLECTION.find_one(
        {"source_id": source_id},
        sort=[("version", -1)]
    )
    
    if not schema_doc:
        # Try to find any schema (fallback for backward compatibility)
        schema_doc = version_manager.get_latest()
        if not schema_doc:
            raise HTTPException(status_code=404, detail=f"No schema found for source_id: {source_id}")
    
    formatted = format_schema_response(schema_doc)
    if not formatted:
        raise HTTPException(status_code=404, detail=f"Schema not found for source_id: {source_id}")
    
    return formatted

@router.get("/schema/history")
async def get_schema_history(
    source_id: str = Query(..., description="Source identifier"),
    limit: Optional[int] = Query(10, description="Maximum number of versions to return")
):
    """
    Get schema history for a source_id with diffs.
    
    Returns list of all schema versions with change diffs.
    """
    # Find all schemas for this source_id
    schemas = list(SCHEMA_COLLECTION.find(
        {"source_id": source_id}
    ).sort("version", -1).limit(limit))
    
    if not schemas:
        # Fallback: get all schemas (backward compatibility)
        schemas = list(SCHEMA_COLLECTION.find().sort("version", -1).limit(limit))
    
    if not schemas:
        raise HTTPException(status_code=404, detail=f"No schema history found for source_id: {source_id}")
    
    history = []
    for schema_doc in schemas:
        formatted = format_schema_response(schema_doc)
        if formatted:
            # Add version and diff info
            formatted["version"] = schema_doc.get("version", 1)
            formatted["created_at"] = schema_doc.get("created_at", "")
            formatted["diff"] = schema_doc.get("diff", {})
            formatted["cause_batch_id"] = schema_doc.get("cause_batch_id", "")
            history.append(formatted)
    
    return {
        "source_id": source_id,
        "total_versions": len(history),
        "schemas": history
    }

