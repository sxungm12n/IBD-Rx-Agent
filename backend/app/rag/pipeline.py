from __future__ import annotations

import logging
import threading

from app.rag.bm25_index import Bm25Index
from app.rag.config import ANSWER_K, BM25_K, FUSION_LIMIT, RRF_K, VECTOR_K, embeddings_path
from app.rag.corpus import load_corpus
from app.rag.embed import embed_query
from app.rag.errors import GuideNotReady
from app.rag.fusion import reciprocal_rank_fusion_scored
from app.rag.generate import generate_answer
from app.rag.rerank import Reranker
from app.rag.types import Passage, RankedPassage
from app.rag.vector_index import VectorIndex

logger = logging.getLogger(__name__)


class Engine:
    def __init__(
        self,
        passages: tuple[Passage, ...],
        bm25: Bm25Index,
        vectors: VectorIndex,
        reranker: Reranker,
    ) -> None:
        self.passages = passages
        self._bm25 = bm25
        self._vectors = vectors
        self._reranker = reranker

    @classmethod
    def load(cls) -> Engine:
        path = embeddings_path()
        logger.info("guide corpus load %s", path)
        passages, matrix = load_corpus(path)
        engine = cls(
            passages=passages,
            bm25=Bm25Index(passages),
            vectors=VectorIndex(matrix),
            reranker=Reranker(),
        )
        logger.info("guide ready passages=%s dim=%s", len(passages), matrix.shape[1])
        return engine

    def answer(
        self, question: str, *, answer_only: bool = False, answer_style: str = "short"
    ) -> tuple[str, list[Passage]]:
        selected = [hit.passage for hit in self.trace(question)["rerank"][:ANSWER_K]]
        logger.info("guide ask sources=%s", [passage.id for passage in selected])
        return (
            generate_answer(question, selected, answer_only=answer_only, answer_style=answer_style),
            selected,
        )

    def bm25_hits(self, question: str, k: int) -> list[RankedPassage]:
        return self._pack(self._bm25.ranked(question, k))

    def vector_hits(self, question: str, k: int) -> list[RankedPassage]:
        return self._pack(self._vectors.ranked(embed_query(question), k))

    def fusion_hits(self, question: str, bm25_k: int, vector_k: int, limit: int) -> list[RankedPassage]:
        lexical = self._bm25.search(question, bm25_k)
        semantic = self._vectors.search(embed_query(question), vector_k)
        return self._pack(reciprocal_rank_fusion_scored([lexical, semantic], k=RRF_K, limit=limit))

    def rerank_hits(self, question: str, passages: list[Passage], k: int) -> list[RankedPassage]:
        scored = self._reranker.scored(question, passages)[:k]
        return [
            RankedPassage(rank=rank, score=score, passage=passage)
            for rank, (passage, score) in enumerate(scored, start=1)
        ]

    def passages_by_ids(self, passage_ids: list[str]) -> list[Passage]:
        lookup = {passage.id: passage for passage in self.passages}
        missing = [passage_id for passage_id in passage_ids if passage_id not in lookup]
        if missing:
            raise ValueError("없는 문서 id: " + ", ".join(missing))
        return [lookup[passage_id] for passage_id in passage_ids]

    def trace(self, question: str) -> dict[str, list[RankedPassage]]:
        lexical = self._bm25.ranked(question, BM25_K)
        semantic = self._vectors.ranked(embed_query(question), VECTOR_K)
        fused = reciprocal_rank_fusion_scored(
            [[index for index, _score in lexical], [index for index, _score in semantic]],
            k=RRF_K,
            limit=FUSION_LIMIT,
        )
        fusion = self._pack(fused)
        return {
            "bm25": self._pack(lexical),
            "vector": self._pack(semantic),
            "fusion": fusion,
            "rerank": self.rerank_hits(question, [hit.passage for hit in fusion], FUSION_LIMIT),
        }

    def _pack(self, ranked: list[tuple[int, float]]) -> list[RankedPassage]:
        return [
            RankedPassage(rank=rank, score=score, passage=self.passages[index])
            for rank, (index, score) in enumerate(ranked, start=1)
        ]


class GuideService:
    def __init__(self) -> None:
        self._warm_lock = threading.Lock()
        self._ask_lock = threading.Lock()
        self._engine: Engine | None = None
        self._error: str | None = None
        self._loading = False
        self._loaded = threading.Event()

    def warm(self) -> None:
        with self._warm_lock:
            if self._engine is not None:
                return
            if self._loading:
                loaded = self._loaded
                waiting = True
            else:
                self._loading = True
                self._error = None
                self._loaded = threading.Event()
                loaded = self._loaded
                waiting = False
        if waiting:
            loaded.wait()
            with self._warm_lock:
                if self._engine is not None:
                    return
                raise GuideNotReady(self._error or "검색 인덱스가 준비되지 않았습니다.")

        try:
            engine = Engine.load()
        except Exception as exc:
            with self._warm_lock:
                self._error = str(exc)
                self._loading = False
            loaded.set()
            raise GuideNotReady(str(exc)) from exc

        with self._warm_lock:
            self._engine = engine
            self._error = None
            self._loading = False
        loaded.set()

    def status(self) -> dict[str, int | str | None]:
        with self._warm_lock:
            if self._engine is not None:
                return {
                    "passages": len(self._engine.passages),
                    "reranker": "ready",
                    "detail": None,
                }
            if self._error and not self._loading:
                return {"passages": None, "reranker": "error", "detail": self._error}
            return {"passages": None, "reranker": "loading", "detail": None}

    def ask(
        self, question: str, *, answer_only: bool = False, answer_style: str = "short"
    ) -> tuple[str, list[Passage]]:
        return self._with_engine(
            question,
            lambda engine, cleaned: engine.answer(
                cleaned, answer_only=answer_only, answer_style=answer_style
            ),
        )

    def bm25(self, question: str, k: int) -> list[RankedPassage]:
        return self._with_engine(question, lambda engine, cleaned: engine.bm25_hits(cleaned, k))

    def vector(self, question: str, k: int) -> list[RankedPassage]:
        return self._with_engine(question, lambda engine, cleaned: engine.vector_hits(cleaned, k))

    def fusion(self, question: str, bm25_k: int, vector_k: int, limit: int) -> list[RankedPassage]:
        return self._with_engine(
            question,
            lambda engine, cleaned: engine.fusion_hits(cleaned, bm25_k, vector_k, limit),
        )

    def rerank(self, question: str, passage_ids: list[str] | None, k: int) -> list[RankedPassage]:
        def run(engine: Engine, cleaned: str) -> list[RankedPassage]:
            if passage_ids:
                passages = engine.passages_by_ids(passage_ids)
            else:
                passages = [hit.passage for hit in engine.fusion_hits(cleaned, BM25_K, VECTOR_K, FUSION_LIMIT)]
            return engine.rerank_hits(cleaned, passages, k)

        return self._with_engine(question, run)

    def trace(self, question: str) -> dict[str, list[RankedPassage]]:
        return self._with_engine(question, lambda engine, cleaned: engine.trace(cleaned))

    def _with_engine(self, question: str, run):
        cleaned = question.strip()
        if len(cleaned) < 2:
            raise ValueError("질문을 두 글자 이상 입력해 주세요.")
        self.warm()
        with self._ask_lock:
            if self._engine is None:
                raise GuideNotReady(self._error or "검색 인덱스가 준비되지 않았습니다.")
            return run(self._engine, cleaned)


guide_service = GuideService()
