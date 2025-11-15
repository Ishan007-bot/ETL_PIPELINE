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
    builder = SchemaBuilder()
    field_stats = {}
    presence = defaultdict(int)
    type_counts = defaultdict(Counter)
    sample_size = len(docs)
    
    for d in docs:
        builder.add_object(d)
        for k, v in d.items():
            presence[k] += 1
            t = _detect_type(v)
            type_counts[k][t] += 1
    
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
    
    if return_stats:
        return schema, field_stats
    return schema
