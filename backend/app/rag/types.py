from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankedPassage:
    rank: int
    score: float
    passage: Passage


@dataclass(frozen=True)
class Passage:
    id: str
    page: int | None
    section: str
    title: str
    text: str
    drugs: tuple[str, ...]
    disease: tuple[str, ...]
    source_title: str

    def search_text(self) -> str:
        """BM25에 넣을 문자열. 제목과 약제명이 본문 앞에 오게 한다."""
        extra = " ".join((*self.drugs, *self.disease))
        return f"{self.title}\n{self.section}\n{extra}\n{self.text}"
