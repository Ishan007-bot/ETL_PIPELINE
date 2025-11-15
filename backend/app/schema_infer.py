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

def infer_schema_from_sample(docs, return_stats=False):
    """Infer schema from sample documents. Always returns a valid schema."""
    try:
        if not docs or len(docs) == 0:
            # Return empty schema
            schema = {"type": "object", "properties": {}}
            return (schema, {}) if return_stats else schema
        
        builder = SchemaBuilder()
        field_stats = {}
        presence = defaultdict(int)
        type_counts = defaultdict(Counter)
        sample_size = len(docs)
        
        for d in docs:
            try:
                if not isinstance(d, dict):
                    # Skip non-dict items
                    continue
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
