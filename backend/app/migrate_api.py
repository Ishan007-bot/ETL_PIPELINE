"""
Migration API endpoint for explicit migrations.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from .migration import route_query_to_schema_version, check_backward_compatibility
from .versioning import VersioningManager

router = APIRouter()
version_manager = VersioningManager()

@router.post("/migrate")
async def migrate_data(
    source_id: str = Query(..., description="Source identifier"),
    target_version: Optional[int] = Query(None, description="Target schema version"),
    dry_run: bool = Query(False, description="If true, only show migration plan without applying")
):
    """
    Explicitly trigger migration for a source_id.
    If target_version is not specified, migrates to latest version.
    """
    # Get current and target schemas
    current_schema = version_manager.get_latest(source_id=source_id)
    if not current_schema:
        raise HTTPException(status_code=404, detail=f"No schema found for source_id: {source_id}")
    
    current_version = current_schema.get("version", 1)
    
    if target_version is None:
        # Migrate to latest
        target_schema = current_schema  # Already latest
        target_version = current_version
    else:
        # Get specific target version
        from pymongo import MongoClient
        import os
        MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
        client = MongoClient(MONGO_URL)
        db = client["chrysalis"]
        SCHEMA_COLLECTION = db["schema_registry"]
        
        target_schema = SCHEMA_COLLECTION.find_one({
            "source_id": source_id,
            "version": target_version
        })
        if not target_schema:
            raise HTTPException(
                status_code=404,
                detail=f"Target schema version {target_version} not found for source_id: {source_id}"
            )
    
    if current_version == target_version:
        return {
            "status": "no_migration_needed",
            "message": f"Already at version {target_version}",
            "current_version": current_version
        }
    
    # Get migration plan
    migration_plan = current_schema.get("migration_plan", {})
    if not migration_plan:
        # Generate migration plan if not stored
        from .migration import generate_migration_plan
        from .schema_diff import compute_schema_diff
        
        old_schema = current_schema.get("schema", {})
        new_schema = target_schema.get("schema", {})
        diff = target_schema.get("diff", {})
        field_stats = target_schema.get("field_stats", {})
        
        migration_plan = generate_migration_plan(
            old_schema,
            new_schema,
            diff,
            field_stats
        )
    
    if dry_run:
        return {
            "status": "dry_run",
            "migration_plan": migration_plan,
            "from_version": current_version,
            "to_version": target_version,
            "message": "Migration plan generated. Set dry_run=false to apply."
        }
    
    # TODO: Apply migration to existing data
    # This would involve:
    # 1. Query all documents with old schema version
    # 2. Apply transformations
    # 3. Update documents with new schema version
    
    return {
        "status": "migration_scheduled",
        "from_version": current_version,
        "to_version": target_version,
        "migration_plan": migration_plan,
        "message": "Migration will be applied to existing data. This is a placeholder for full migration implementation."
    }

