from pymongo import MongoClient
import os

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
client = MongoClient(MONGO_URL)
db = client["chrysalis"]
RAW_COLLECTION = db["raw_data"]

class StorageManager:
    def insert_many(self, docs):
        if docs:
            RAW_COLLECTION.insert_many(docs)
        return True
