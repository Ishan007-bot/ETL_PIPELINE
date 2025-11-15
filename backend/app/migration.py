"""
Migration strategy and backward compatibility module.
Handles schema evolution, data transformations, and versioned queries.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from .versioning import VersioningManager

version_manager = VersioningManager()

def generate_migration_plan(
    old_schema: Dict[str, Any],
    new_schema: Dict[str, Any],
    diff: Any,
    field_stats: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate a migration plan for schema changes.
    Returns transformation rules and compatibility notes.
    """
    migration_plan = {
        "migration_type": "automatic",
        "backward_compatible": True,
        "transformations": [],
        "warnings": [],
        "data_loss_risk": False
    }
    
    if not old_schema:
        migration_plan["migration_type"] = "initial_load"
        return migration_plan
    
    transformations = []
    warnings = []
    data_loss_risk = False
    
    # Handle added fields
    added = getattr(diff, "added", {})
    for field_name, field_info in added.items():
        transformations.append({
            "action": "add_field",
            "field": field_name,
            "default_value": None,
            "nullable": True,
            "description": f"New field '{field_name}' added"
        })
    
    # Handle removed fields
    removed = getattr(diff, "removed", {})
    for field_name, field_info in removed.items():
        prev_presence = field_info.get("prev_presence", 1.0)
        if prev_presence >= 0.5:  # Field was present in >50% of docs
            warnings.append({
                "severity": "high",
                "message": f"Field '{field_name}' was removed but was present in {prev_presence*100:.1f}% of previous data"
            })
            data_loss_risk = True
        
        transformations.append({
            "action": "remove_field",
            "field": field_name,
            "preserve_in_legacy": True,  # Keep in versioned storage
            "description": f"Field '{field_name}' removed (preserved in legacy schema)"
        })
    
    # Handle changed fields
    changed = getattr(diff, "changed", {})
    for field_name, field_info in changed.items():
        old_type = field_info.get("old", {}).get("type", "unknown")
        new_type = field_info.get("new", {}).get("type", "unknown")
        new_dom_pct = field_info.get("new_dom_pct", 1.0)
        
        # Type conversion rules
        conversion_rule = None
        if old_type == "string" and new_type in ["number", "integer"]:
            conversion_rule = {
                "type": "cast",
                "function": "try_parse_number",
                "fallback": "null"
            }
            warnings.append({
                "severity": "medium",
                "message": f"Field '{field_name}' type changed from {old_type} to {new_type}. Some values may fail conversion."
            })
        elif old_type in ["number", "integer"] and new_type == "string":
            conversion_rule = {
                "type": "cast",
                "function": "to_string",
                "fallback": "null"
            }
        elif old_type == "string" and new_type == "date":
            conversion_rule = {
                "type": "cast",
                "function": "parse_date",
                "fallback": "keep_original"
            }
        
        transformations.append({
            "action": "transform_field",
            "field": field_name,
            "old_type": old_type,
            "new_type": new_type,
            "conversion_rule": conversion_rule,
            "confidence": new_dom_pct,
            "description": f"Field '{field_name}' type changed from {old_type} to {new_type}"
        })
    
    migration_plan["transformations"] = transformations
    migration_plan["warnings"] = warnings
    migration_plan["data_loss_risk"] = data_loss_risk
    migration_plan["backward_compatible"] = len(removed) == 0 and not data_loss_risk
    
    return migration_plan

def apply_migration_transform(
    document: Dict[str, Any],
    migration_plan: Dict[str, Any],
    target_version: int
) -> Dict[str, Any]:
    """
    Apply migration transformations to a document.
    """
    transformed = document.copy()
    
    for transformation in migration_plan.get("transformations", []):
        action = transformation.get("action")
        field = transformation.get("field")
        
        if action == "add_field":
            if field not in transformed:
                transformed[field] = transformation.get("default_value")
        
        elif action == "remove_field":
            if field in transformed:
                # Preserve in legacy field
                if "_legacy_fields" not in transformed:
                    transformed["_legacy_fields"] = {}
                transformed["_legacy_fields"][field] = transformed.pop(field)
        
        elif action == "transform_field":
            if field in transformed:
                conversion_rule = transformation.get("conversion_rule")
                if conversion_rule:
                    old_value = transformed[field]
                    new_value = apply_conversion(old_value, conversion_rule)
                    transformed[field] = new_value
    
    # Mark with target version
    transformed["_schema_version"] = target_version
    
    return transformed

def apply_conversion(value: Any, conversion_rule: Dict[str, Any]) -> Any:
    """
    Apply a type conversion rule to a value.
    """
    if value is None:
        return None
    
    func_type = conversion_rule.get("type")
    function = conversion_rule.get("function")
    fallback = conversion_rule.get("fallback", "null")
    
    try:
        if function == "try_parse_number":
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                # Try to parse as number
                try:
                    if '.' in value:
                        return float(value)
                    else:
                        return int(value)
                except:
                    pass
        
        elif function == "to_string":
            return str(value)
        
        elif function == "parse_date":
            if isinstance(value, str):
                from dateparser import parse
                parsed = parse(value)
                if parsed:
                    return parsed.isoformat()
        
    except Exception:
        pass
    
    # Apply fallback
    if fallback == "null":
        return None
    elif fallback == "keep_original":
        return value
    else:
        return value

def check_backward_compatibility(
    old_schema: Dict[str, Any],
    new_schema: Dict[str, Any],
    query_fields: List[str]
) -> Tuple[bool, List[str]]:
    """
    Check if a query using old schema fields is compatible with new schema.
    Returns: (is_compatible, missing_fields)
    """
    if not old_schema:
        return True, []
    
    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    
    missing_fields = []
    for field in query_fields:
        if field in old_props and field not in new_props:
            missing_fields.append(field)
    
    return len(missing_fields) == 0, missing_fields

def route_query_to_schema_version(
    source_id: str,
    query_fields: List[str],
    target_version: Optional[int] = None
) -> Dict[str, Any]:
    """
    Route a query to the appropriate schema version.
    If target_version is None, finds the latest compatible version.
    """
    from pymongo import MongoClient
    import os
    
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
    client = MongoClient(MONGO_URL)
    db = client["chrysalis"]
    SCHEMA_COLLECTION = db["schema_registry"]
    
    if target_version:
        # Get specific version
        schema_doc = SCHEMA_COLLECTION.find_one({
            "source_id": source_id,
            "version": target_version
        })
        if schema_doc:
            return {
                "schema_version": target_version,
                "schema": schema_doc.get("schema", {}),
                "compatible": True
            }
    
    # Find latest compatible version
    schemas = list(SCHEMA_COLLECTION.find(
        {"source_id": source_id}
    ).sort("version", -1))
    
    for schema_doc in schemas:
        schema = schema_doc.get("schema", {})
        compatible, missing = check_backward_compatibility(
            schema,
            schema,  # Same schema is always compatible
            query_fields
        )
        if compatible:
            return {
                "schema_version": schema_doc.get("version", 1),
                "schema": schema,
                "compatible": True
            }
    
    # Fallback to latest
    latest = version_manager.get_latest(source_id=source_id)
    if latest:
        return {
            "schema_version": latest.get("version", 1),
            "schema": latest.get("schema", {}),
            "compatible": False,
            "warning": "Some query fields may not exist in current schema"
        }
    
    return {
        "schema_version": 1,
        "schema": {},
        "compatible": False
    }

def create_migration_metadata(
    source_id: str,
    from_version: int,
    to_version: int,
    migration_plan: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create migration metadata record.
    """
    return {
        "source_id": source_id,
        "from_version": from_version,
        "to_version": to_version,
        "migration_plan": migration_plan,
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending"
    }

