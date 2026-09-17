# Hugging Face Spaces (Docker SDK) build for DocQuery.
# Also works as a plain Dockerfile anywhere else that runs containers.

FROM python:3.12-slim

# HF Spaces convention: containers run as a non-root user with UID 1000.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Build tools: not strictly required for every dependency, but included so
# a package without a prebuilt wheel for this platform doesn't fail the
# build with no fallback.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/user/app

COPY --chown=user requirements.txt .
USER user
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# HF Spaces (Docker SDK) always routes traffic to port 7860. HOST must be
# 0.0.0.0 to be reachable from outside the container. RELOAD must be off
# in any deployed/production environment. HF_HOME keeps the downloaded
# embedding model's cache inside a path this user can actually write to.
ENV HOST=0.0.0.0 \
    PORT=7860 \
    RELOAD=false \
    HF_HOME=/home/user/app/.cache/huggingface

EXPOSE 7860

CMD ["python", "-m", "backend.main"]