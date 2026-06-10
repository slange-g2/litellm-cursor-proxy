FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.sh .
RUN chmod +x run.sh

# Defaults suited to running in a container:
# - bind on all interfaces so the mapped port is reachable from the host
# - reach a LiteLLM proxy running on the Docker host
ENV LISTEN_HOST=0.0.0.0 \
    LISTEN_PORT=8787 \
    UPSTREAM_BASE_URL=http://host.docker.internal:4000

EXPOSE 8787

CMD ["./run.sh"]
