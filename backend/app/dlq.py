import redis
import os
import orjson
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=False)

DLQ_NAME = "chrysalis:dlq"

def send_to_dlq(payload, reason="unknown"):
    msg = {
        "payload": payload,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        r.lpush(DLQ_NAME, orjson.dumps(msg))
    except Exception as e:
        print("DLQ push failed", e)
