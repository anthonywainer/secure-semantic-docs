FROM apache/superset:4.0.2

USER root

# Python dependencies — installed before config files so a config-only change
# does not trigger a reinstall
RUN pip install --no-cache-dir trino sqlalchemy-trino

# Superset config and init script
COPY config/superset/superset_config.py /app/superset_home/superset_config.py
COPY docker/superset/init_superset.sh /app/init_superset.sh
RUN chmod +x /app/init_superset.sh

ENV SUPERSET_CONFIG_PATH=/app/superset_home/superset_config.py
ENV PYTHONPATH=/app/superset_home:${PYTHONPATH}

USER superset
