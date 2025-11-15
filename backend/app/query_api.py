"""
Query API endpoints for LLM-driven query execution.
"""
from fastapi import APIRouter, HTTPException, Body, Query
from typing import Optional, Dict, Any
import uuid
from datetime import datetime
import time
from .llm_query import translate_nl_to_query, validate_query
from .query_executor import execute_mongodb_query, execute_count_query
from .versioning import VersioningManager
from .migration import route_query_to_schema_version
from .security import validate_nl_query, sanitize_query, validate_source_id
from .app_logging import get_logger, log_query_execution, log_error, log_security_event
import redis
import os
import orjson

logger = get_logger("chrysalis.query")

router = APIRouter()

version_manager = VersioningManager()

# For async query storage
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=False)
QUERY_RESULTS_KEY = "chrysalis:query_results"

@router.post("/query")
async def execute_query(
    source_id: str = Body(..., description="Source identifier"),
    nl_query: Optional[str] = Body(None, description="Natural language query"),
    db_query: Optional[Dict[str, Any]] = Body(None, description="Direct database query (optional)"),
    db_type: str = Body("mongodb", description="Target database type"),
    async_mode: bool = Body(False, description="If true, return query_id for async retrieval")
):
    """
    Execute a query. Can accept natural language query (translated via LLM) or direct DB query.
    
    If async_mode=true, returns query_id that can be polled via GET /records.
    """
    # Validate source_id
    if not validate_source_id(source_id):
        log_security_event(logger, "invalid_source_id", {"source_id": source_id})
        raise HTTPException(status_code=400, detail="Invalid source_id format")
    
    # Get schema for this source_id
    schema_doc = version_manager.get_latest(source_id=source_id)
    if not schema_doc:
        raise HTTPException(status_code=404, detail=f"No schema found for source_id: {source_id}")
    
    schema = schema_doc.get("enhanced_schema", schema_doc.get("schema", {}))
    
    # Translate NL query if provided
    if nl_query:
        # Validate NL query
        nl_validation = validate_nl_query(nl_query)
        if not nl_validation["valid"]:
            log_security_event(logger, "invalid_nl_query", {"reason": nl_validation.get("reason")})
            raise HTTPException(status_code=400, detail=nl_validation.get("reason", "Invalid query"))
        
        translation_result = translate_nl_to_query(nl_query, schema, source_id, db_type)
        
        # Validate query
        validation = validate_query(translation_result, schema)
        if not validation["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Query references invalid fields: {validation['invalid_fields']}"
            )
        
        db_query = translation_result.get("query")
        query_type = translation_result.get("query_type", "find")
        query_fields = translation_result.get("fields", [])
        confidence = translation_result.get("confidence", 0.0)
    else:
        if not db_query:
            raise HTTPException(status_code=400, detail="Either nl_query or db_query must be provided")
        
        # Sanitize direct query
        try:
            db_query = sanitize_query(db_query)
        except HTTPException:
            raise
        except Exception as e:
            log_security_event(logger, "query_sanitization_failed", {"error": str(e)})
            raise HTTPException(status_code=400, detail="Query sanitization failed")
        
        query_type = "find"
        query_fields = []
        confidence = 1.0
    
    # Route to appropriate schema version
    routing = route_query_to_schema_version(source_id, query_fields)
    schema_version = routing.get("schema_version")
    
    # Execute query
    start_time = time.time()
    try:
        if query_type == "count":
            result = execute_count_query(db_query, source_id=source_id, schema_version=schema_version)
        else:
            result = execute_mongodb_query(db_query, source_id=source_id, schema_version=schema_version, db_type=db_type)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Log query execution
        log_query_execution(
            logger,
            source_id,
            query_type,
            db_type,
            result.get("count", len(result.get("results", []))),
            execution_time_ms
        )
        
        if async_mode:
            # Store result and return query_id
            query_id = str(uuid.uuid4())
            result_data = {
                "query_id": query_id,
                "source_id": source_id,
                "result": result,
                "created_at": datetime.utcnow().isoformat(),
                "status": "completed"
            }
            r.setex(
                f"{QUERY_RESULTS_KEY}:{query_id}",
                3600,  # 1 hour TTL
                orjson.dumps(result_data)
            )
            
            return {
                "status": "accepted",
                "query_id": query_id,
                "message": "Query executed. Use GET /records to retrieve results."
            }
        else:
            # Return results immediately
            return {
                "status": "ok",
                "source_id": source_id,
                "query_type": query_type,
                "confidence": confidence,
                "result": result
            }
    except Exception as e:
        log_error(logger, "query_execution_error", f"Query execution failed: {str(e)}", {
            "source_id": source_id,
            "query_type": query_type,
            "db_type": db_type
        })
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")

@router.get("/records")
async def get_records(
    source_id: Optional[str] = Query(None, description="Source identifier"),
    query_id: Optional[str] = Query(None, description="Query ID from async query"),
    schema_version: Optional[int] = Query(None, description="Filter by schema version"),
    limit: int = Query(100, description="Maximum number of records")
):
    """
    Get query results. Can retrieve async query results by query_id, or fetch records directly.
    """
    if query_id:
        # Retrieve async query result
        result_data = r.get(f"{QUERY_RESULTS_KEY}:{query_id}")
        if not result_data:
            raise HTTPException(status_code=404, detail=f"Query result not found for query_id: {query_id}")
        
        try:
            result = orjson.loads(result_data)
            return {
                "status": "ok",
                "query_id": query_id,
                "result": result.get("result", {})
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse query result: {str(e)}")
    
    else:
        # Direct record fetch
        if not source_id:
            raise HTTPException(status_code=400, detail="Either query_id or source_id must be provided")
        
        # Simple fetch query
        query = {}
        result = execute_mongodb_query(
            query,
            source_id=source_id,
            schema_version=schema_version,
            limit=limit
        )
        
        return {
            "status": "ok",
            "source_id": source_id,
            "result": result
        }

