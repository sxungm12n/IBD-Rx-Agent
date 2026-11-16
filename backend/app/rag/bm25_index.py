from __future__ import annotations

from app.rag.errors import GuideNotReady
from app.rag.tokenize import tokenize
from app.rag.types import Passage


class Bm25Index:
    def __init__(self, passages: tuple[Passage, ...]) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise GuideNotReady("rank-bm25가 설치되어 있지 않습니다.") from exc
        documents = [tokenize(passage.search_text()) for passage in passages]
        self._bm25 = BM25Okapi(documents)

    def ranked(self, question: str, k: int) -> list[tuple[int, float]]:
        tokens = tokenize(question)
        if not tokens or k <= 0:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        return [(int(index), float(scores[index])) for index in order if scores[index] > 0][:k]

    def search(self, question: str, k: int) -> list[int]:
        return [index for index, _score in self.ranked(question, k)]
