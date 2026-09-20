# A private Render service running Ollama, so the backend's
# ai/ollama_client.py can keep talking to a plain http://.../api endpoint
# exactly like it does against localhost today — no code changes needed
# beyond pointing OLLAMA_HOST at this service (see render.yaml).
#
# IMPORTANT — read before deploying:
# qwen3:8b (the model config.py defaults to) needs ~6-8GB of RAM just to
# load. Render's cheaper plans don't have that much RAM and there's no
# GPU, so inference will be slow and a small/Standard instance may OOM.
# Either size this service up (Pro plan or higher) or swap OLLAMA_MODEL
# to something smaller, e.g. "qwen2.5:1.5b" or "phi3:mini", which run
# fine on 2-4GB.

FROM ollama/ollama:latest

# Which model to pre-pull at container start. Overridable per-deploy via
# Render's env vars without rebuilding the image.
ENV OLLAMA_MODEL=qwen3:8b

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 11434
ENTRYPOINT ["/entrypoint.sh"]
