from __future__ import annotations

import os

from app.rag.config import RERANK_MAX_LENGTH, RERANKER_MODEL
from app.rag.errors import GuideNotReady
from app.rag.types import Passage


def rerank_device() -> str:
    """재랭커를 올릴 장치. RAG_RERANK_DEVICE(auto·cuda·cuda:0·mps·cpu)로 고른다. 기본 auto = CUDA → MPS → CPU.

    GPU 서버에서 vLLM과 같은 GPU를 잡지 않게 하려면 RAG_RERANK_DEVICE=cuda:0 처럼 번호를 준다.
    정밀도는 장치와 상관없이 float32 그대로 둔다(이전 실행과 순위가 바뀌지 않게).
    """
    want = os.environ.get("RAG_RERANK_DEVICE", "auto").strip().lower() or "auto"
    if want != "auto":
        return want
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


class Reranker:
    def __init__(self) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise GuideNotReady("sentence-transformers가 설치되어 있지 않습니다.") from exc
        self.device = rerank_device()
        self._model = CrossEncoder(RERANKER_MODEL, max_length=RERANK_MAX_LENGTH, device=self.device)

    def scored(self, question: str, passages: list[Passage]) -> list[tuple[Passage, float]]:
        if not passages:
            return []
        pairs = [(question, passage.text) for passage in passages]
        raw = self._model.predict(pairs, show_progress_bar=False)
        import numpy as np

        scores = np.asarray(raw, dtype=np.float32).reshape(-1)
        order = np.argsort(scores)[::-1]
        return [(passages[int(index)], float(scores[int(index)])) for index in order]

    def order(self, question: str, passages: list[Passage]) -> list[Passage]:
        return [passage for passage, _score in self.scored(question, passages)]
