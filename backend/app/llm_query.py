"""
LLM integration for natural language to database query translation.
"""
import os
from typing import Dict, Any, Optional
import json

# Try to import OpenAI, but make it optional
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

def translate_nl_to_query(
    natural_language: str,
    schema: Dict[str, Any],
    source_id: str,
    db_type: str = "mongodb"
) -> Dict[str, Any]:
    """
    Translate natural language query to database query using LLM.
    
    Returns:
    {
        "query": "translated_query",
        "query_type": "find|aggregate|count",
        "fields": ["field1", "field2"],
        "confidence": 0.95
    }
    """
    # Check if OpenAI is available
    if not OPENAI_AVAILABLE:
        # Fallback: Simple rule-based translation
        return translate_nl_to_query_fallback(natural_language, schema, db_type)
    
    # Get OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Fallback if no API key
        return translate_nl_to_query_fallback(natural_language, schema, db_type)
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Build schema context
        schema_context = build_schema_context(schema)
        
        # Create prompt
        prompt = f"""You are a database query translator. Translate the following natural language query to a {db_type} query.

Schema:
{schema_context}

Natural Language Query: {natural_language}

Return a JSON object with:
- "query": The {db_type} query (as a string or JSON object)
- "query_type": One of "find", "aggregate", "count", "update", "delete"
- "fields": List of fields referenced in the query
- "confidence": Confidence score (0.0-1.0)

For MongoDB, return queries in MongoDB query format (JSON objects).
For PostgreSQL, return SQL queries.
For Neo4j, return Cypher queries.

Only return the JSON object, no other text."""

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            messages=[
                {"role": "system", "content": "You are a database query translator. Always return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        result = json.loads(result_text)
        result["llm_model"] = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        return result
        
    except Exception as e:
        print(f"LLM translation failed: {e}")
        # Fallback to rule-based
        return translate_nl_to_query_fallback(natural_language, schema, db_type)

def build_schema_context(schema: Dict[str, Any]) -> str:
    """Build a text description of the schema for LLM context."""
    if "fields" in schema:
        # Use enhanced schema
        fields_desc = []
        for field in schema["fields"]:
            field_desc = f"- {field.get('name')}: {field.get('type')}"
            if field.get("nullable"):
                field_desc += " (nullable)"
            if field.get("example"):
                field_desc += f" (example: {field.get('example')})"
            fields_desc.append(field_desc)
        return "\n".join(fields_desc)
    else:
        # Use basic schema
        properties = schema.get("properties", {})
        fields_desc = []
        for field_name, field_schema in properties.items():
            field_type = field_schema.get("type", "unknown")
            fields_desc.append(f"- {field_name}: {field_type}")
        return "\n".join(fields_desc)

def translate_nl_to_query_fallback(
    natural_language: str,
    schema: Dict[str, Any],
    db_type: str = "mongodb"
) -> Dict[str, Any]:
    """
    Fallback rule-based translation when LLM is not available.
    """
    nl_lower = natural_language.lower()
    
    # Extract fields from schema
    fields = []
    if "fields" in schema:
        fields = [f.get("name") for f in schema["fields"]]
    else:
        fields = list(schema.get("properties", {}).keys())
    
    # Simple pattern matching
    query = {}
    query_type = "find"
    referenced_fields = []
    
    # Check for count queries
    if "count" in nl_lower or "how many" in nl_lower:
        query_type = "count"
        query = {}
    
    # Check for specific field mentions
    for field in fields:
        if field.lower() in nl_lower:
            referenced_fields.append(field)
    
    # Check for filter conditions
    if "where" in nl_lower or "filter" in nl_lower or "with" in nl_lower:
        # Try to extract filter conditions
        # This is very basic - real implementation would need NLP
        query = {}
    
    # Build MongoDB query
    if db_type == "mongodb":
        mongo_query = query if query else {}
    else:
        mongo_query = str(query)
    
    return {
        "query": mongo_query,
        "query_type": query_type,
        "fields": referenced_fields,
        "confidence": 0.6,  # Lower confidence for fallback
        "method": "fallback"
    }

def validate_query(query: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that the query references valid fields in the schema.
    """
    valid_fields = []
    if "fields" in schema:
        valid_fields = [f.get("name") for f in schema["fields"]]
    else:
        valid_fields = list(schema.get("properties", {}).keys())
    
    referenced_fields = query.get("fields", [])
    invalid_fields = [f for f in referenced_fields if f not in valid_fields]
    
    return {
        "valid": len(invalid_fields) == 0,
        "invalid_fields": invalid_fields,
        "warnings": []
    }

