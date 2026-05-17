# Chroma Docker Configuration

Chroma runs as a Docker service in `docker-compose.yml`.

## Service definition

Service name: `chroma`
Image: `chromadb/chroma:latest`
Port: `8000:8000`

## Volume mount

`./runtime/vector_store/chroma:/chroma/chroma` — persistent storage for Chroma index data.

## Role

Chroma is a **fast vector candidate index only**. It is NOT the source of truth.
The encrypted lakehouse Gold layer remains the authoritative source.

## What Chroma stores

- Embedding vectors (decoded float vectors)
- Safe metadata: chunk_id, document_id, classification, allowed_roles, department
-

## Client code

See `src/secure_semantic_docs/vector_store/chroma_client.py`.

Set connection via environment variables:

- `CHROMA_HOST` (default: localhost)
- `CHROMA_PORT` (default: 8000)
