"""
Singleton access to the embedding model.

`lru_cache` guarantees the (fairly expensive to load) HuggingFace model is
only initialized once per process, no matter how many requests use it --
this addresses the "avoid loading the embedding model unnecessarily
multiple times" performance requirement.

Note on HF_TOKEN: we do not pass it around manually. huggingface_hub reads
the HF_TOKEN environment variable itself (verified: huggingface_hub.get_token()
picks it up automatically once it's in the process environment, which
python-dotenv's load_dotenv() already ensures). The public MiniLM model used
here doesn't require a token at all; it only matters if EMBEDDING_MODEL is
changed to a gated model.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from backend import config


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
