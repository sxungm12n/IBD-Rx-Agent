from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rag.errors import GuideError, GuideNotReady
from app.rag.pipeline import guide_service

router = APIRouter(prefix="/api/guide", tags=["guide"])


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    answer_only: bool = False
    # 평가용 답 형식 (answer_only일 때): short=단답(A·A2형), case=환자 판정(C형), drugs=약제 선택(D형), open_drugs=보기 없는 약제 선택(D2형)
    answer_style: Literal["short", "case", "drugs", "open_drugs"] = "short"


class SourceOut(BaseModel):
    id: str
    page: int | None
    section: str
    title: str
    text: str
    drugs: list[str]
    disease: list[str]


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]


class StatusResponse(BaseModel):
    passages: int | None
    reranker: str
    detail: str | None


@router.get("/status", response_model=StatusResponse)
def status() -> dict[str, int | str | None]:
    return guide_service.status()


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest) -> AskResponse:
    try:
        answer, passages = await asyncio.to_thread(
            guide_service.ask,
            body.question,
            answer_only=body.answer_only,
            answer_style=body.answer_style,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GuideNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GuideError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AskResponse(
        answer=answer,
        sources=[
            SourceOut(
                id=passage.id,
                page=passage.page,
                section=passage.section,
                title=passage.title,
                text=passage.text,
                drugs=list(passage.drugs),
                disease=list(passage.disease),
            )
            for passage in passages
        ],
    )
