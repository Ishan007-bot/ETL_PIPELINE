from genson import SchemaBuilder
from collections import defaultdict, Counter

def _detect_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"

def _is_structured_document(doc):
    """Check if document is structured (has nested objects/arrays)."""
    if not isinstance(doc, dict):
        return False
    for v in doc.values():
        if isinstance(v, (dict, list)) and not isinstance(v, str):
            return True
    return False

def _fix_type_union(schema, field_stats):
    """
    Post-process schema to create proper type unions when mixed types are detected.
    Prioritizes structured types (array, object) over primitive types when both exist.
    """
    if "properties" not in schema:
        return schema
    
    for field_name, field_schema in schema["properties"].items():
        if field_name not in field_stats:
            continue
        
        type_counts = field_stats[field_name].get("type_counts", {})
        if not type_counts or len(type_counts) <= 1:
            continue
        
        # Get all types for this field
        all_types = list(type_counts.keys())
        current_type = field_schema.get("type")
        
        # If field has both structured types (array/object) and primitive types (string/number)
        # Prioritize structured types
        structured_types = [t for t in all_types if t in ["array", "object"]]
        primitive_types = [t for t in all_types if t in ["string", "number", "integer", "boolean"]]
        
        if structured_types and primitive_types:
            # If structured type appears in at least 20% of documents, use it
            total_count = sum(type_counts.values())
            structured_count = sum(type_counts.get(t, 0) for t in structured_types)
            
            if structured_count / total_count >= 0.2:  # At least 20% are structured
                # Use structured type, but allow union if significant primitive presence
                if structured_count / total_count >= 0.5:  # Majority are structured
                    field_schema["type"] = structured_types[0]  # Use the structured type
                else:
                    # Create union: structured type + most common primitive
                    most_common_primitive = max(primitive_types, key=lambda t: type_counts.get(t, 0))
                    field_schema["type"] = [structured_types[0], most_common_primitive]
            elif len(all_types) > 1:
                # Create union of all types (GenSON should do this, but ensure it happens)
                if not isinstance(current_type, list):
                    field_schema["type"] = sorted(all_types)  # Union type
        
        # If GenSON already created a union, ensure it's sorted
        elif isinstance(current_type, list):
            field_schema["type"] = sorted(current_type)
    
    return schema

def infer_schema_from_sample(docs, return_stats=False):
    """Infer schema from sample documents. Always returns a valid schema."""
    try:
        if not docs or len(docs) == 0:
            # Return empty schema
            schema = {"type": "object", "properties": {}}
            return (schema, {}) if return_stats else schema
        
        # Separate structured documents from unstructured
        structured_docs = []
        unstructured_docs = []
        
        for d in docs:
            if not isinstance(d, dict):
                continue
            if _is_structured_document(d):
                structured_docs.append(d)
            else:
                unstructured_docs.append(d)
        
        # Weight structured documents more heavily
        # Add structured docs multiple times to give them more weight
        weighted_docs = structured_docs * 3 + unstructured_docs  # 3x weight for structured
        
        builder = SchemaBuilder()
        field_stats = {}
        presence = defaultdict(int)
        type_counts = defaultdict(Counter)
        sample_size = len(docs)  # Use original sample size for stats
        
        # Build schema from weighted documents
        for d in weighted_docs:
            try:
                builder.add_object(d)
                for k, v in d.items():
                    try:
                        presence[k] += 1
                        t = _detect_type(v)
                        type_counts[k][t] += 1
                    except Exception:
                        continue
            except Exception:
                continue
        
        for k in presence:
            field_stats[k] = {
                "present": presence[k],
                "present_pct": presence[k] / sample_size if sample_size else 0,
                "type_counts": dict(type_counts[k])
            }
        
        schema = builder.to_schema()
        
        # Post-process to fix type unions (prioritize structured types)
        schema = _fix_type_union(schema, field_stats)
        
        # normalize
        if "$schema" in schema:
            schema.pop("$schema", None)
        if "properties" in schema:
            props = schema["properties"]
            schema["properties"] = {k: props[k] for k in sorted(props.keys())}
        else:
            # Ensure properties exist
            schema["properties"] = {}
        
        if return_stats:
            return schema, field_stats
        return schema
    except Exception as e:
        # Fallback: return minimal valid schema
        print(f"Error in schema inference: {e}")
        schema = {"type": "object", "properties": {}}
        return (schema, {}) if return_stats else schema
