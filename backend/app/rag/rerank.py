from __future__ import annotations

from app.rag.config import RERANK_MAX_LENGTH, RERANKER_MODEL
from app.rag.errors import GuideNotReady
from app.rag.types import Passage


class Reranker:
    def __init__(self) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise GuideNotReady("sentence-transformers가 설치되어 있지 않습니다.") from exc
        self._model = CrossEncoder(RERANKER_MODEL, max_length=RERANK_MAX_LENGTH)

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
