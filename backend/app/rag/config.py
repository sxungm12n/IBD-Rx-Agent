from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

EMBEDDING_MODEL = "text-embedding-3-large"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

BM25_K = 12
VECTOR_K = 12
RRF_K = 60
FUSION_LIMIT = 20
ANSWER_K = 5
RERANK_MAX_LENGTH = 2048


def chat_model() -> str:
    return os.environ.get("RAG_CHAT_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"


def embeddings_path() -> Path:
    override = os.environ.get("RAG_EMBEDDINGS", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "data" / "RAG" / "IBD_insurance_guide_2024.embeddings.jsonl"


def openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    env_file = embeddings_path().parent / ".env"
    if env_file.is_file():
        load_dotenv(env_file)
    return os.environ.get("OPENAI_API_KEY", "").strip()
