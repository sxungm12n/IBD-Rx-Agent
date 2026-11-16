from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rag.config import ANSWER_K, BM25_K, FUSION_LIMIT, VECTOR_K
from app.rag.errors import GuideError, GuideNotReady
from app.rag.pipeline import guide_service
from app.rag.types import RankedPassage

router = APIRouter(prefix="/api/guide/stages", tags=["guide-stages"])

_MAX_K = 70


class StageQuery(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=BM25_K, ge=1, le=_MAX_K)


class FusionQuery(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    bm25_k: int = Field(default=BM25_K, ge=1, le=_MAX_K)
    vector_k: int = Field(default=VECTOR_K, ge=1, le=_MAX_K)
    limit: int = Field(default=FUSION_LIMIT, ge=1, le=_MAX_K)


class RerankQuery(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    passage_ids: list[str] | None = None
    k: int = Field(default=FUSION_LIMIT, ge=1, le=_MAX_K)


class AskQuery(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class HitOut(BaseModel):
    rank: int
    score: float
    id: str
    page: int | None
    section: str
    title: str
    text: str
    drugs: list[str]
    disease: list[str]


class StageResponse(BaseModel):
    stage: str
    question: str
    hits: list[HitOut]


class TraceResponse(BaseModel):
    question: str
    answer_k: int
    bm25: list[HitOut]
    vector: list[HitOut]
    fusion: list[HitOut]
    rerank: list[HitOut]


def _hits(ranked: list[RankedPassage]) -> list[HitOut]:
    return [
        HitOut(
            rank=hit.rank,
            score=round(hit.score, 6),
            id=hit.passage.id,
            page=hit.passage.page,
            section=hit.passage.section,
            title=hit.passage.title,
            text=hit.passage.text,
            drugs=list(hit.passage.drugs),
            disease=list(hit.passage.disease),
        )
        for hit in ranked
    ]


async def _call(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GuideNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GuideError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/bm25", response_model=StageResponse)
async def bm25(body: StageQuery) -> StageResponse:
    hits = await _call(guide_service.bm25, body.question, body.k)
    return StageResponse(stage="bm25", question=body.question.strip(), hits=_hits(hits))


@router.post("/vector", response_model=StageResponse)
async def vector(body: StageQuery) -> StageResponse:
    hits = await _call(guide_service.vector, body.question, body.k)
    return StageResponse(stage="vector", question=body.question.strip(), hits=_hits(hits))


@router.post("/fusion", response_model=StageResponse)
async def fusion(body: FusionQuery) -> StageResponse:
    hits = await _call(guide_service.fusion, body.question, body.bm25_k, body.vector_k, body.limit)
    return StageResponse(stage="fusion", question=body.question.strip(), hits=_hits(hits))


@router.post("/rerank", response_model=StageResponse)
async def rerank(body: RerankQuery) -> StageResponse:
    hits = await _call(guide_service.rerank, body.question, body.passage_ids, body.k)
    return StageResponse(stage="rerank", question=body.question.strip(), hits=_hits(hits))


@router.post("/trace", response_model=TraceResponse)
async def trace(body: AskQuery) -> TraceResponse:
    stages = await _call(guide_service.trace, body.question)
    return TraceResponse(
        question=body.question.strip(),
        answer_k=ANSWER_K,
        bm25=_hits(stages["bm25"]),
        vector=_hits(stages["vector"]),
        fusion=_hits(stages["fusion"]),
        rerank=_hits(stages["rerank"]),
    )
