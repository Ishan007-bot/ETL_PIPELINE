"""
Schema metadata generation for multiple database compatibility.
Generates DDL for PostgreSQL, MongoDB schemas, Neo4j schemas, and JSON Schema.
"""
from typing import Dict, Any, List, Optional
import json

def detect_primary_key_candidates(fields: Dict[str, Any], sample_docs: List[Dict[str, Any]]) -> List[str]:
    """
    Detect potential primary key candidates based on:
    - Field names (id, _id, uuid, etc.)
    - Uniqueness in sample
    - Non-null percentage
    """
    candidates = []
    
    # Common primary key field names
    common_pk_names = ['id', '_id', 'uuid', 'key', 'pk', 'identifier', 'slug']
    
    for field_name, field_schema in fields.items():
        score = 0.0
        
        # Check field name
        field_lower = field_name.lower()
        if any(pk_name in field_lower for pk_name in common_pk_names):
            score += 0.5
        
        # Check uniqueness in sample
        if sample_docs:
            values = [doc.get(field_name) for doc in sample_docs if field_name in doc]
            # Filter out unhashable types (dicts, lists) and convert to hashable
            hashable_values = []
            for v in values:
                if isinstance(v, (dict, list)):
                    # Convert to JSON string for hashing
                    import json
                    hashable_values.append(json.dumps(v, sort_keys=True, default=str))
                else:
                    hashable_values.append(v)
            unique_values = set(hashable_values)
            uniqueness_ratio = len(unique_values) / len(values) if values else 0
            if uniqueness_ratio >= 0.95:  # 95% unique
                score += 0.3
            elif uniqueness_ratio >= 0.8:  # 80% unique
                score += 0.15
        
        # Check non-null percentage
        non_null_count = sum(1 for v in values if v is not None)
        non_null_ratio = non_null_count / len(values) if values else 0
        if non_null_ratio >= 0.95:
            score += 0.2
        
        if score >= 0.5:
            candidates.append((field_name, score))
    
    # Sort by score and return field names
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [name for name, score in candidates[:3]]  # Top 3 candidates

def generate_postgresql_ddl(schema: Dict[str, Any], table_name: str = "data_table") -> str:
    """
    Generate PostgreSQL DDL from JSON schema.
    """
    if "properties" not in schema:
        return ""
    
    columns = []
    properties = schema.get("properties", {})
    
    for field_name, field_schema in properties.items():
        col_def = f'    "{field_name}"'
        
        # Determine PostgreSQL type
        field_type = field_schema.get("type", "text")
        
        if isinstance(field_type, list):
            # Union type - use text for safety
            col_def += " TEXT"
        elif field_type == "string":
            # Check for date format
            if "format" in field_schema and field_schema["format"] == "date":
                col_def += " DATE"
            else:
                max_length = field_schema.get("maxLength", 255)
                if max_length and max_length <= 255:
                    col_def += f" VARCHAR({max_length})"
                else:
                    col_def += " TEXT"
        elif field_type == "number" or field_type == "integer":
            if "format" in field_schema and field_schema["format"] == "int32":
                col_def += " INTEGER"
            else:
                col_def += " NUMERIC"
        elif field_type == "boolean":
            col_def += " BOOLEAN"
        elif field_type == "array":
            col_def += " JSONB"
        elif field_type == "object":
            col_def += " JSONB"
        else:
            col_def += " TEXT"
        
        # Nullable
        if not field_schema.get("nullable", True):
            col_def += " NOT NULL"
        
        columns.append(col_def)
    
    ddl = f"CREATE TABLE {table_name} (\n"
    ddl += ",\n".join(columns)
    ddl += "\n);"
    
    return ddl

def generate_mongodb_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate MongoDB collection schema (JSON Schema format for MongoDB).
    """
    mongodb_schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "properties": {}
        }
    }
    
    if "properties" not in schema:
        return mongodb_schema
    
    properties = schema.get("properties", {})
    
    for field_name, field_schema in properties.items():
        mongo_prop = {}
        
        field_type = field_schema.get("type", "string")
        
        # Map JSON Schema types to BSON types
        if isinstance(field_type, list):
            mongo_prop["bsonType"] = ["string", "int", "double", "bool", "object", "array", "null"]
        elif field_type == "string":
            mongo_prop["bsonType"] = "string"
        elif field_type == "number" or field_type == "integer":
            mongo_prop["bsonType"] = ["int", "double"]
        elif field_type == "boolean":
            mongo_prop["bsonType"] = "bool"
        elif field_type == "array":
            mongo_prop["bsonType"] = "array"
        elif field_type == "object":
            mongo_prop["bsonType"] = "object"
        else:
            mongo_prop["bsonType"] = "string"
        
        # Description
        if "description" in field_schema:
            mongo_prop["description"] = field_schema["description"]
        
        mongodb_schema["$jsonSchema"]["properties"][field_name] = mongo_prop
    
    return mongodb_schema

def generate_neo4j_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate Neo4j node/relationship schema.
    """
    neo4j_schema = {
        "node_labels": ["DataNode"],
        "properties": {}
    }
    
    if "properties" not in schema:
        return neo4j_schema
    
    properties = schema.get("properties", {})
    
    for field_name, field_schema in properties.items():
        prop_def = {}
        
        field_type = field_schema.get("type", "string")
        
        # Map to Neo4j types
        if field_type == "string":
            prop_def["type"] = "String"
        elif field_type == "number" or field_type == "integer":
            prop_def["type"] = "Float"  # Neo4j uses Float for numbers
        elif field_type == "boolean":
            prop_def["type"] = "Boolean"
        elif field_type == "array":
            prop_def["type"] = "List"
        else:
            prop_def["type"] = "String"
        
        neo4j_schema["properties"][field_name] = prop_def
    
    return neo4j_schema

def generate_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate standard JSON Schema (already in this format, but enhance it).
    """
    json_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": []
    }
    
    # Add required fields (non-nullable)
    if "properties" in schema:
        for field_name, field_schema in schema["properties"].items():
            if not field_schema.get("nullable", True):
                json_schema["required"].append(field_name)
    
    return json_schema

def enhance_schema_with_metadata(
    schema: Dict[str, Any],
    field_stats: Dict[str, Any],
    sample_docs: List[Dict[str, Any]],
    source_offsets: Optional[Dict[str, List[int]]] = None
) -> Dict[str, Any]:
    """
    Enhance schema with metadata: confidence scores, primary keys, field paths, examples.
    """
    enhanced_schema = schema.copy()
    
    if "properties" not in enhanced_schema:
        enhanced_schema["properties"] = {}
    
    enhanced_fields = []
    properties = enhanced_schema.get("properties", {})
    
    # Detect primary key candidates
    pk_candidates = detect_primary_key_candidates(properties, sample_docs)
    
    for field_name, field_schema in properties.items():
        field_meta = {
            "name": field_name,
            "path": f"$.{field_name}",  # JSONPath
            "type": field_schema.get("type", "string"),
            "nullable": field_schema.get("nullable", True),
            "example": None,
            "confidence": 0.0,
            "source_offsets": source_offsets.get(field_name, []) if source_offsets else []
        }
        
        # Get example value from sample docs
        for doc in sample_docs[:5]:
            if field_name in doc:
                field_meta["example"] = doc[field_name]
                break
        
        # Get confidence from field_stats
        if field_name in field_stats:
            stats = field_stats[field_name]
            presence_pct = stats.get("present_pct", 0)
            
            # Type consistency
            type_counts = stats.get("type_counts", {})
            if type_counts:
                total = sum(type_counts.values())
                dominant_type_pct = max(type_counts.values()) / total if total > 0 else 0
                field_meta["confidence"] = presence_pct * dominant_type_pct
            else:
                field_meta["confidence"] = presence_pct
        
        # Check if primary key candidate
        if field_name in pk_candidates:
            field_meta["primary_key_candidate"] = True
            field_meta["primary_key_score"] = next(
                (score for name, score in zip(pk_candidates, [1.0, 0.8, 0.6]) if name == field_name),
                0.5
            )
        
        # Add suggested index if high confidence and frequently queried
        if field_meta["confidence"] >= 0.8:
            field_meta["suggested_index"] = True
        
        enhanced_fields.append(field_meta)
    
    enhanced_schema["fields"] = enhanced_fields
    enhanced_schema["primary_key_candidates"] = pk_candidates
    
    return enhanced_schema

def generate_db_compatibility_metadata(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate database compatibility metadata for all supported databases.
    """
    compatible_dbs = []
    
    # Check if schema is simple enough for relational DBs
    has_nested_objects = any(
        isinstance(field_schema.get("type"), str) and field_schema.get("type") == "object"
        for field_schema in schema.get("properties", {}).values()
    )
    
    has_arrays = any(
        isinstance(field_schema.get("type"), str) and field_schema.get("type") == "array"
        for field_schema in schema.get("properties", {}).values()
    )
    
    # PostgreSQL - good for most schemas
    compatible_dbs.append("postgresql")
    
    # MongoDB - good for nested structures
    compatible_dbs.append("mongodb")
    
    # Neo4j - can handle any structure
    compatible_dbs.append("neo4j")
    
    return {
        "compatible_dbs": compatible_dbs,
        "postgresql_ddl": generate_postgresql_ddl(schema),
        "mongodb_schema": generate_mongodb_schema(schema),
        "neo4j_schema": generate_neo4j_schema(schema),
        "json_schema": generate_json_schema(schema)
    }

