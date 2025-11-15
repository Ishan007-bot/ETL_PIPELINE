"""
Data cleaning and canonicalization module.
Handles field normalization, type coercion, date parsing, and data quality scoring.
"""
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import dateparser
from collections import defaultdict

def normalize_field_name(name: str) -> str:
    """Normalize field names to snake_case."""
    if not name or not isinstance(name, str):
        return name
    
    # Remove special characters except alphanumeric and underscore
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    
    # Convert camelCase to snake_case
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', name)
    
    # Convert to lowercase
    name = name.lower()
    
    # Remove multiple underscores
    name = re.sub(r'_+', '_', name)
    
    # Remove leading/trailing underscores
    name = name.strip('_')
    
    return name if name else 'unnamed_field'

def detect_and_coerce_type(value: Any) -> Tuple[Any, str, float]:
    """
    Detect and coerce value to appropriate type.
    Returns: (coerced_value, detected_type, confidence)
    """
    if value is None:
        return None, "null", 1.0
    
    if isinstance(value, bool):
        return value, "boolean", 1.0
    
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value, "number", 1.0
    
    if isinstance(value, str):
        str_value = value.strip()
        
        # Empty string
        if not str_value:
            return None, "null", 1.0
        
        # Try boolean
        if str_value.lower() in ['true', 'false', 'yes', 'no', '1', '0']:
            bool_val = str_value.lower() in ['true', 'yes', '1']
            return bool_val, "boolean", 0.9
        
        # Try number
        try:
            # Integer
            if str_value.isdigit() or (str_value.startswith('-') and str_value[1:].isdigit()):
                return int(str_value), "number", 0.95
        except:
            pass
        
        try:
            # Float
            float_val = float(str_value)
            return float_val, "number", 0.95
        except:
            pass
        
        # Try date
        date_result = parse_date(str_value)
        if date_result:
            return date_result, "date", 0.85
        
        # Default to string
        return str_value, "string", 1.0
    
    if isinstance(value, dict):
        return value, "object", 1.0
    
    if isinstance(value, list):
        return value, "array", 1.0
    
    return value, "unknown", 0.5

def parse_date(date_str: str) -> Optional[str]:
    """
    Parse date string and return ISO format.
    Returns None if not a valid date.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    # Common date patterns
    date_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
        r'\d{2}-\d{2}-\d{4}',  # MM-DD-YYYY
        r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
    ]
    
    # Check if string matches a date pattern
    matches_pattern = any(re.search(pattern, date_str) for pattern in date_patterns)
    
    if matches_pattern:
        try:
            parsed = dateparser.parse(date_str)
            if parsed:
                return parsed.isoformat()
        except:
            pass
    
    # Try dateparser for more flexible parsing
    try:
        parsed = dateparser.parse(date_str)
        if parsed:
            return parsed.isoformat()
    except:
        pass
    
    return None

def clean_document(doc: Dict[str, Any], normalize_names: bool = True) -> Dict[str, Any]:
    """
    Clean a single document:
    - Normalize field names
    - Coerce types
    - Handle nulls
    - Remove empty fields (optional)
    """
    cleaned = {}
    quality_scores = {}
    
    for key, value in doc.items():
        # Normalize field name
        if normalize_names:
            clean_key = normalize_field_name(key)
        else:
            clean_key = key
        
        # Skip system fields (they start with _)
        if clean_key.startswith('_'):
            cleaned[key] = value
            continue
        
        # Detect and coerce type
        coerced_value, detected_type, confidence = detect_and_coerce_type(value)
        
        # Store quality score
        quality_scores[clean_key] = {
            "original_type": type(value).__name__,
            "detected_type": detected_type,
            "confidence": confidence,
            "was_null": value is None or (isinstance(value, str) and not value.strip())
        }
        
        # Handle nulls
        if coerced_value is None:
            cleaned[clean_key] = None
        elif isinstance(coerced_value, dict):
            # Recursively clean nested objects
            cleaned[clean_key] = clean_document(coerced_value, normalize_names)
        elif isinstance(coerced_value, list):
            # Clean array elements
            cleaned[clean_key] = [clean_document(item, normalize_names) if isinstance(item, dict) else item for item in coerced_value]
        else:
            cleaned[clean_key] = coerced_value
    
    # Add quality metadata
    cleaned['_quality_metadata'] = quality_scores
    
    return cleaned

def remove_duplicates(documents: List[Dict[str, Any]], key_fields: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], int]:
    """
    Remove duplicate documents.
    If key_fields provided, use those for comparison.
    Otherwise, compare entire documents.
    Returns: (cleaned_documents, duplicates_removed_count)
    """
    seen = set()
    unique_docs = []
    duplicates_removed = 0
    
    for doc in documents:
        if key_fields:
            # Create hash from key fields
            key_values = tuple(sorted([str(doc.get(k, '')) for k in key_fields]))
        else:
            # Create hash from entire document (excluding metadata)
            doc_copy = {k: v for k, v in doc.items() if not k.startswith('_')}
            key_values = tuple(sorted(doc_copy.items()))
        
        if key_values not in seen:
            seen.add(key_values)
            unique_docs.append(doc)
        else:
            duplicates_removed += 1
    
    return unique_docs, duplicates_removed

def compute_data_quality_score(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute overall data quality metrics for a collection of documents.
    """
    if not documents:
        return {
            "total_documents": 0,
            "quality_score": 0.0,
            "field_coverage": {},
            "null_percentage": {},
            "type_consistency": {}
        }
    
    total_docs = len(documents)
    field_stats = defaultdict(lambda: {
        "count": 0,
        "null_count": 0,
        "types": defaultdict(int),
        "confidences": []
    })
    
    # Aggregate statistics
    for doc in documents:
        quality_meta = doc.get('_quality_metadata', {})
        for field, stats in quality_meta.items():
            field_stats[field]["count"] += 1
            if stats.get("was_null"):
                field_stats[field]["null_count"] += 1
            field_stats[field]["types"][stats.get("detected_type", "unknown")] += 1
            field_stats[field]["confidences"].append(stats.get("confidence", 0.0))
    
    # Compute metrics
    field_coverage = {}
    null_percentage = {}
    type_consistency = {}
    
    for field, stats in field_stats.items():
        coverage = stats["count"] / total_docs
        null_pct = stats["null_count"] / stats["count"] if stats["count"] > 0 else 0
        
        # Type consistency: percentage of most common type
        if stats["types"]:
            most_common_type_count = max(stats["types"].values())
            type_consistency_pct = most_common_type_count / stats["count"]
        else:
            type_consistency_pct = 0.0
        
        # Average confidence
        avg_confidence = sum(stats["confidences"]) / len(stats["confidences"]) if stats["confidences"] else 0.0
        
        field_coverage[field] = coverage
        null_percentage[field] = null_pct
        type_consistency[field] = {
            "consistency": type_consistency_pct,
            "dominant_type": max(stats["types"].items(), key=lambda x: x[1])[0] if stats["types"] else "unknown",
            "avg_confidence": avg_confidence
        }
    
    # Overall quality score (weighted average)
    if field_coverage:
        avg_coverage = sum(field_coverage.values()) / len(field_coverage)
        avg_consistency = sum([v["consistency"] for v in type_consistency.values()]) / len(type_consistency) if type_consistency else 0
        avg_confidence = sum([v["avg_confidence"] for v in type_consistency.values()]) / len(type_consistency) if type_consistency else 0
        
        # Quality score: coverage * consistency * confidence
        quality_score = avg_coverage * avg_consistency * avg_confidence
    else:
        quality_score = 0.0
    
    return {
        "total_documents": total_docs,
        "quality_score": quality_score,
        "field_coverage": field_coverage,
        "null_percentage": null_percentage,
        "type_consistency": type_consistency
    }

def clean_documents(documents: List[Dict[str, Any]], 
                    normalize_names: bool = True,
                    remove_duplicates_flag: bool = True,
                    key_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Main cleaning function for a batch of documents.
    Returns cleaned documents and quality metrics.
    """
    # Clean each document
    cleaned_docs = [clean_document(doc, normalize_names) for doc in documents]
    
    # Remove duplicates if requested
    duplicates_removed = 0
    if remove_duplicates_flag:
        cleaned_docs, duplicates_removed = remove_duplicates(cleaned_docs, key_fields)
    
    # Compute quality metrics
    quality_metrics = compute_data_quality_score(cleaned_docs)
    quality_metrics["duplicates_removed"] = duplicates_removed
    
    return {
        "cleaned_documents": cleaned_docs,
        "quality_metrics": quality_metrics
    }

