#!/bin/sh
set -e

echo "==> Running bronze ingestion..."
python -m secure_semantic_docs.bronze_ingestion

echo "==> Running silver ingestion..."
python -m secure_semantic_docs.silver_ingestion

echo "==> Running gold ingestion..."
python -m secure_semantic_docs.gold_ingestion

echo "==> Running demo..."
python -m secure_semantic_docs.demo
