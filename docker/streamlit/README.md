# Streamlit Service

Streamlit runs as a Docker service in `docker-compose.yml` under the `ui` profile.

## Service definition

Service name: `streamlit-ui`
Port: `8501:8501`
Profile: `ui`

## Start

```bash
docker compose --profile ui up streamlit-ui
```

## Role

Streamlit is a **controlled semantic retrieval UI only**.

- Natural language query
- Graph-first, vector-first, or hybrid retrieval strategy
- Role-based result filtering
- Audit log visibility
- No raw SQL editor
- No direct database access

## Source

`src/secure_semantic_docs/ui/streamlit_app.py`
`src/secure_semantic_docs/query_ui.py` (entry point)
