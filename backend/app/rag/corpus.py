from __future__ import annotations

import json
from pathlib import Path

from app.rag.errors import GuideNotReady
from app.rag.types import Passage


def load_corpus(path: Path):
    import numpy as np

    if not path.is_file():
        raise GuideNotReady(f"임베딩 파일을 찾을 수 없습니다: {path}")

    passages: list[Passage] = []
    vectors: list[list[float]] = []
    models: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            embedding = record.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise GuideNotReady(f"{path.name}:{line_no} embedding이 없습니다.")
            model = str(record.get("embedding_model") or "")
            if model:
                models.add(model)
            page = record.get("page")
            drugs = record.get("drugs") or []
            disease = record.get("disease") or []
            passages.append(
                Passage(
                    id=str(record.get("id") or f"line-{line_no}"),
                    page=page if isinstance(page, int) else None,
                    section=str(record.get("section") or ""),
                    title=str(record.get("title") or ""),
                    text=str(record.get("text") or "").strip(),
                    drugs=tuple(str(item) for item in drugs),
                    disease=tuple(str(item) for item in disease),
                    source_title=str(record.get("source_title") or ""),
                )
            )
            vectors.append(embedding)

    if not passages:
        raise GuideNotReady(f"{path.name}에 기록이 없습니다.")
    if len(models) > 1:
        raise GuideNotReady(f"임베딩 모델이 섞여 있습니다: {', '.join(sorted(models))}")

    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(passages):
        raise GuideNotReady("임베딩 차원이 고르지 않습니다.")
    return tuple(passages), matrix
