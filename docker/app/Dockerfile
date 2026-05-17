FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_NO_CACHE=1

WORKDIR /app

# System packages — changes infrequently; cached independently of app code
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl default-jdk-headless \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

ENV JAVA_HOME=/usr/lib/jvm/default-java

# External JARs — download before copying source so a source-only change does not
# trigger a re-download
ARG ICEBERG_VERSION=1.10.0
ARG ICEBERG_RUNTIME_ARTIFACT=iceberg-spark-runtime-4.0_2.13
ARG ICEBERG_JAR_URL=https://repo1.maven.org/maven2/org/apache/iceberg/${ICEBERG_RUNTIME_ARTIFACT}/${ICEBERG_VERSION}/${ICEBERG_RUNTIME_ARTIFACT}-${ICEBERG_VERSION}.jar

RUN mkdir -p /opt/spark/jars \
    && curl -fsSL -o /opt/spark/jars/iceberg-spark-runtime.jar "${ICEBERG_JAR_URL}"

# Dependency manifests only — cached independently of application source changes
COPY requirements.txt pyproject.toml README.md /app/
RUN uv pip install -r requirements.txt

# Application source
COPY src/ /app/src/
RUN uv pip install --no-deps -e .

# Streamlit configuration — disables file watcher to avoid triggering optional
# package imports (e.g. torchvision) that have no Python 3.14 wheel
COPY .streamlit/ /app/.streamlit/

# Entrypoint script
COPY docker/app/entrypoint.sh /entrypoint.sh

# Non-root runtime user
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/runtime/lakehouse /app/runtime/logs /app/runtime/metadata \
    && chmod +x /entrypoint.sh \
    && chown -R appuser:appuser /app

ENV DOCSEC_PROJECT_ROOT=/app

USER appuser

ENTRYPOINT ["/entrypoint.sh"]
