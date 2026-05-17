# Chroma Vector Index

## Role in the architecture

Chroma is a **fast vector candidate index**. It is not the source of truth.

The encrypted lakehouse Gold layer remains the single authoritative source.
Chroma enables sub-second approximate-nearest-neighbor (ANN) search over
embedding vectors without requiring full Parquet scan at query time.

## What is stored in Chroma

| Field            | Stored | Notes                  |
|------------------|--------|------------------------|
| Embedding vector | YES    | Decoded float32 vector |
| chunk_id         | YES    | Safe reference key     |
| document_id      | YES    | Safe reference key     |
| classification   | YES    | For metadata filtering |
| allowed_roles    | YES    | For pre-filter hints   |
| department       | YES    | For metadata filtering |
| owner            | YES    | Safe metadata          |
| version          | YES    | Safe metadata          |

## Security boundary

Chroma returns **candidate chunk IDs** only. The retrieval service then:

1. Fetches full records from the encrypted lakehouse.
2. Applies permission filtering (`can_access_record`).
3. Decrypts only authorized embeddings.
4. Answers supported exact questions from governed extracted facts.
5. Returns sanitized results.

Chroma **never stores** chunk text or plaintext content. It is a vector index only.
Permission enforcement is always done in the Python permission layer — never
delegated to Chroma.

## Running Chroma

```bash
docker compose up chroma
```

Client configuration:

```bash
CHROMA_HOST=localhost   # or 'chroma' inside Docker network
CHROMA_PORT=8000
```

## Client module

`src/secure_semantic_docs/vector_store/chroma_client.py`
