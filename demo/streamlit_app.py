import streamlit as st
from pymongo import MongoClient
import os
import orjson
import redis

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
client = MongoClient(MONGO_URL)
db = client["chrysalis"]

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=False)

DLQ_NAME = "chrysalis:dlq"

st.set_page_config(page_title="Chrysalis Demo", layout="wide")

st.title("Chrysalis+ — Dynamic ETL Demo")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("Schema Registry")
    schemas = list(db.schema_registry.find().sort("version", -1))
    if schemas:
        for s in schemas:
            with st.expander(f"Version {s['version']} — {s['created_at']}"):
                st.subheader("Diff")
                st.json(s.get("diff", {}))
                st.subheader("Sample docs")
                st.json(s.get("sample_docs", []))
    else:
        st.info("No schemas yet. Ingest a batch.")

with col2:
    st.header("Ingested Documents (sample)")
    docs = list(db.raw_data.find().limit(50))
    st.write(f"Showing {len(docs)} documents")
    for d in docs:
        st.json(d)

st.sidebar.header("DLQ (dead letters)")
dlq = r.lrange(DLQ_NAME, 0, 50)
if not dlq:
    st.sidebar.info("No DLQ entries")
else:
    for idx, item in enumerate(dlq):
        try:
            obj = orjson.loads(item)
            with st.sidebar.expander(f"DLQ {idx} — {obj.get('reason')}"):
                st.json(obj)
        except Exception:
            st.sidebar.text(item)

