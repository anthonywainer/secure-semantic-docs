# Streamlit service

Streamlit is configured as a Docker service in the root `docker-compose.yml` file.
It is not built from a separate image and reuses the `secure-semantic-docs:py314` image.

## Access

- URL: http://localhost:8501

## Usage

1. Build the shared app image first:
   ```bash
   docker build -f docker/app/Dockerfile -t secure-semantic-docs:py314 .
   ```
2. Start the governed Streamlit UI:
   ```bash
   docker compose --profile ui up streamlit-ui --no-build
   ```
