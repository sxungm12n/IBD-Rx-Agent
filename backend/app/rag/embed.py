from __future__ import annotations

from app.rag.config import EMBEDDING_MODEL, openai_api_key
from app.rag.errors import GuideError, GuideNotReady


def embed_query(text: str) -> np.ndarray:
    key = openai_api_key()
    if not key:
        raise GuideNotReady("OPENAI_API_KEY가 없습니다.")
    try:
        from openai import OpenAI, OpenAIError
    except ImportError as exc:
        raise GuideNotReady("openai 패키지가 설치되어 있지 않습니다.") from exc

    try:
        response = OpenAI(api_key=key).embeddings.create(model=EMBEDDING_MODEL, input=text)
    except OpenAIError as exc:
        raise GuideError(f"질문 임베딩에 실패했습니다. {exc}") from exc
    import numpy as np

    return np.asarray(response.data[0].embedding, dtype=np.float32)
