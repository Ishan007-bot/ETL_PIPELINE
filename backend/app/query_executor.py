"""
Query executor for running queries against MongoDB.
"""
from typing import Dict, Any, List, Optional
from pymongo import MongoClient
import os
import json

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
client = MongoClient(MONGO_URL)
db = client["chrysalis"]
RAW_COLLECTION = db["raw_data"]

def execute_mongodb_query(
    query: Dict[str, Any],
    source_id: Optional[str] = None,
    schema_version: Optional[int] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Execute a MongoDB query against the raw_data collection.
    
    Args:
        query: MongoDB query object or string
        source_id: Filter by source_id
        schema_version: Filter by schema version
        limit: Maximum number of results
    
    Returns:
        {
            "results": [...],
            "count": 123,
            "query_executed": {...}
        }
    """
    # Build filter
    filter_query = {}
    
    if source_id:
        filter_query["_source_id"] = source_id
    
    if schema_version:
        filter_query["_schema_version"] = schema_version
    
    # Parse query if it's a string
    if isinstance(query, str):
        try:
            query_obj = json.loads(query)
        except:
            # If not JSON, treat as simple field filter
            query_obj = {}
    else:
        query_obj = query
    
    # Merge query with filters
    if query_obj:
        filter_query.update(query_obj)
    
    # Execute query
    try:
        # Determine query type
        if "$aggregate" in str(query_obj) or "$group" in str(query_obj):
            # Aggregation pipeline
            pipeline = [{"$match": filter_query}]
            if isinstance(query_obj, list):
                pipeline.extend(query_obj)
            results = list(RAW_COLLECTION.aggregate(pipeline, limit=limit))
            count = len(results)
        else:
            # Find query
            results = list(RAW_COLLECTION.find(filter_query).limit(limit))
            count = RAW_COLLECTION.count_documents(filter_query)
        
        # Convert ObjectId to string for JSON serialization
        for result in results:
            if "_id" in result:
                result["_id"] = str(result["_id"])
        
        return {
            "results": results,
            "count": count,
            "query_executed": filter_query,
            "limit": limit
        }
    except Exception as e:
        raise ValueError(f"Query execution failed: {str(e)}")

def execute_count_query(
    query: Dict[str, Any],
    source_id: Optional[str] = None,
    schema_version: Optional[int] = None
) -> Dict[str, Any]:
    """
    Execute a count query.
    """
    filter_query = {}
    
    if source_id:
        filter_query["_source_id"] = source_id
    
    if schema_version:
        filter_query["_schema_version"] = schema_version
    
    if isinstance(query, str):
        try:
            query_obj = json.loads(query)
            filter_query.update(query_obj)
        except:
            pass
    elif query:
        filter_query.update(query)
    
    count = RAW_COLLECTION.count_documents(filter_query)
    
    return {
        "count": count,
        "query_executed": filter_query
    }

