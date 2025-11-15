"""
Multi-database support for PostgreSQL, MongoDB, and Neo4j.
Handles connections, schema creation, and data ingestion into multiple databases.
"""
import os
from typing import Dict, Any, List, Optional
from pymongo import MongoClient

# PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import execute_values
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Neo4j
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

# MongoDB (already available)
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
mongo_client = MongoClient(MONGO_URL)
mongo_db = mongo_client["chrysalis"]

# PostgreSQL connection
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@postgres:5432/chrysalis")

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

class PostgreSQLManager:
    """PostgreSQL database manager."""
    
    def __init__(self):
        self.conn = None
        if PSYCOPG2_AVAILABLE:
            try:
                self.conn = psycopg2.connect(POSTGRES_URL)
            except Exception as e:
                print(f"PostgreSQL connection failed: {e}")
                self.conn = None
    
    def create_table_from_schema(self, schema: Dict[str, Any], table_name: str, source_id: str):
        """Create PostgreSQL table from schema."""
        if not self.conn or not PSYCOPG2_AVAILABLE:
            return False
        
        try:
            from .schema_metadata import generate_postgresql_ddl
            ddl = generate_postgresql_ddl(schema, table_name)
            
            # Add source_id and schema version columns
            ddl = ddl.replace(
                ");",
                f',\n    "source_id" VARCHAR(255) NOT NULL,\n    "schema_version" INTEGER,\n    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n);'
            )
            
            # Create table if not exists
            cursor = self.conn.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
            cursor.execute(ddl)
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"PostgreSQL table creation failed: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def insert_documents(self, table_name: str, documents: List[Dict[str, Any]]):
        """Insert documents into PostgreSQL table."""
        if not self.conn or not PSYCOPG2_AVAILABLE or not documents:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            # Get column names from first document
            columns = list(documents[0].keys())
            
            # Prepare values
            values = []
            for doc in documents:
                row = [doc.get(col) for col in columns]
                values.append(row)
            
            # Insert
            quoted_columns = [f'"{col}"' for col in columns]
            insert_query = f'INSERT INTO {table_name} ({", ".join(quoted_columns)}) VALUES %s'
            execute_values(cursor, insert_query, values)
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            print(f"PostgreSQL insert failed: {e}")
            if self.conn:
                self.conn.rollback()
            return False
    
    def execute_query(self, query: str):
        """Execute a SQL query."""
        if not self.conn or not PSYCOPG2_AVAILABLE:
            return None
        
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            cursor.close()
            
            # Convert to list of dicts
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            print(f"PostgreSQL query execution failed: {e}")
            return None

class Neo4jManager:
    """Neo4j database manager."""
    
    def __init__(self):
        self.driver = None
        if NEO4J_AVAILABLE:
            try:
                self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            except Exception as e:
                print(f"Neo4j connection failed: {e}")
                self.driver = None
    
    def create_schema(self, schema: Dict[str, Any], label: str, source_id: str):
        """Create Neo4j node schema (constraints/indexes)."""
        if not self.driver or not NEO4J_AVAILABLE:
            return False
        
        try:
            with self.driver.session() as session:
                # Create constraint on source_id
                session.run(
                    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.source_id IS NOT NULL"
                )
                
                # Create indexes on common fields
                properties = schema.get("properties", {})
                for field_name in list(properties.keys())[:5]:  # Index first 5 fields
                    session.run(
                        f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{field_name})"
                    )
            
            return True
        except Exception as e:
            print(f"Neo4j schema creation failed: {e}")
            return False
    
    def insert_documents(self, label: str, documents: List[Dict[str, Any]]):
        """Insert documents as Neo4j nodes."""
        if not self.driver or not NEO4J_AVAILABLE or not documents:
            return False
        
        try:
            with self.driver.session() as session:
                for doc in documents:
                    # Create node with all properties
                    props = {k: v for k, v in doc.items() if not k.startswith('_')}
                    props_str = ", ".join([f"n.{k} = ${k}" for k in props.keys()])
                    
                    query = f"""
                    CREATE (n:{label} {{
                        {", ".join([f"{k}: ${k}" for k in props.keys()])}
                    }})
                    """
                    session.run(query, props)
            
            return True
        except Exception as e:
            print(f"Neo4j insert failed: {e}")
            return False
    
    def execute_query(self, cypher_query: str, parameters: Optional[Dict] = None):
        """Execute a Cypher query."""
        if not self.driver or not NEO4J_AVAILABLE:
            return None
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, parameters or {})
                records = []
                for record in result:
                    records.append(dict(record))
                return records
        except Exception as e:
            print(f"Neo4j query execution failed: {e}")
            return None

class MultiDBManager:
    """Manager for multiple database backends."""
    
    def __init__(self):
        self.postgres = PostgreSQLManager()
        self.neo4j = Neo4jManager()
        self.mongo = mongo_db  # Already connected
    
    def create_schemas(self, schema: Dict[str, Any], source_id: str, compatible_dbs: List[str]):
        """Create schemas in all compatible databases."""
        table_name = f"data_{source_id.replace('-', '_')}"
        label = f"Data_{source_id.replace('-', '_')}"
        
        results = {
            "mongodb": True,  # Already using MongoDB
            "postgresql": False,
            "neo4j": False
        }
        
        if "postgresql" in compatible_dbs:
            results["postgresql"] = self.postgres.create_table_from_schema(
                schema, table_name, source_id
            )
        
        if "neo4j" in compatible_dbs:
            results["neo4j"] = self.neo4j.create_schema(schema, label, source_id)
        
        return results
    
    def insert_to_databases(
        self,
        documents: List[Dict[str, Any]],
        source_id: str,
        compatible_dbs: List[str]
    ):
        """Insert documents into all compatible databases."""
        table_name = f"data_{source_id.replace('-', '_')}"
        label = f"Data_{source_id.replace('-', '_')}"
        
        results = {
            "mongodb": True,  # Already inserted
            "postgresql": False,
            "neo4j": False
        }
        
        if "postgresql" in compatible_dbs:
            results["postgresql"] = self.postgres.insert_documents(table_name, documents)
        
        if "neo4j" in compatible_dbs:
            results["neo4j"] = self.neo4j.insert_documents(label, documents)
        
        return results
    
    def execute_query_multi_db(
        self,
        query: Dict[str, Any],
        source_id: str,
        db_type: str = "mongodb"
    ):
        """Execute query on specified database type."""
        if db_type == "postgresql":
            if isinstance(query, dict):
                # Convert MongoDB query to SQL (simplified)
                sql = self._mongo_to_sql(query, source_id)
                return self.postgres.execute_query(sql)
            elif isinstance(query, str):
                return self.postgres.execute_query(query)
        elif db_type == "neo4j":
            if isinstance(query, dict):
                # Convert MongoDB query to Cypher (simplified)
                cypher = self._mongo_to_cypher(query, source_id)
                return self.neo4j.execute_query(cypher)
            elif isinstance(query, str):
                return self.neo4j.execute_query(query)
        else:
            # MongoDB (default)
            from .query_executor import execute_mongodb_query
            return execute_mongodb_query(query, source_id=source_id)
    
    def _mongo_to_sql(self, mongo_query: Dict[str, Any], source_id: str) -> str:
        """Convert MongoDB query to SQL (simplified)."""
        table_name = f"data_{source_id.replace('-', '_')}"
        
        # Basic conversion
        where_clauses = []
        for key, value in mongo_query.items():
            if key == "_source_id":
                continue
            if isinstance(value, dict):
                if "$gt" in value:
                    where_clauses.append(f'"{key}" > {value["$gt"]}')
                elif "$lt" in value:
                    where_clauses.append(f'"{key}" < {value["$lt"]}')
                elif "$eq" in value:
                    where_clauses.append(f'"{key}" = \'{value["$eq"]}\'')
            else:
                where_clauses.append(f'"{key}" = \'{value}\'')
        
        where = " AND ".join(where_clauses) if where_clauses else "1=1"
        return f'SELECT * FROM {table_name} WHERE source_id = \'{source_id}\' AND {where} LIMIT 100'
    
    def _mongo_to_cypher(self, mongo_query: Dict[str, Any], source_id: str) -> str:
        """Convert MongoDB query to Cypher (simplified)."""
        label = f"Data_{source_id.replace('-', '_')}"
        
        # Basic conversion
        where_clauses = [f"n.source_id = '{source_id}'"]
        for key, value in mongo_query.items():
            if key == "_source_id":
                continue
            if isinstance(value, dict):
                if "$gt" in value:
                    where_clauses.append(f"n.{key} > {value['$gt']}")
                elif "$lt" in value:
                    where_clauses.append(f"n.{key} < {value['$lt']}")
            else:
                where_clauses.append(f"n.{key} = '{value}'")
        
        where = " AND ".join(where_clauses)
        return f"MATCH (n:{label}) WHERE {where} RETURN n LIMIT 100"

