#!/usr/bin/env bash

set -e

API_URL=${API_URL:-"http://localhost:8000"}

echo "Posting Batch A (no drift)..."
curl -s -X POST "$API_URL/ingest" -H "Content-Type: application/json" --data-binary @../fixtures/batch_A.json | jq

sleep 2

echo "Posting Batch B (add field currency)..."
curl -s -X POST "$API_URL/ingest" -H "Content-Type: application/json" --data-binary @../fixtures/batch_B.json | jq

sleep 2

echo "Posting Batch C (price type string)..."
curl -s -X POST "$API_URL/ingest" -H "Content-Type: application/json" --data-binary @../fixtures/batch_C.json | jq

echo "Done. Open Streamlit at http://localhost:8501 to view results."

