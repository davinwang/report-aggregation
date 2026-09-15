# FastAPI backend — python:3.12-slim, deps from requirements.txt.
# Schema + default users are created at boot by the app lifespan (init_db).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PYTHONPATH=/srv/backend

WORKDIR /srv/backend

# Install runtime deps first (layer caching — only rebuilds when requirements.txt changes).
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

# App sources + alembic scaffolding + entrypoint.
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY deploy/backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Normalize CRLF (Windows checkouts) so /bin/sh can execute the script.
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
