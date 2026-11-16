from __future__ import annotations


def reciprocal_rank_fusion_scored(
    rankings: list[list[int]],
    *,
    k: int = 60,
    limit: int = 20,
) -> list[tuple[int, float]]:
    """여러 순위 목록을 Reciprocal Rank Fusion으로 합치고 점수를 함께 돌려준다."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)
    return [(doc_id, scores[doc_id]) for doc_id in ordered[:limit]]


def reciprocal_rank_fusion(
    rankings: list[list[int]],
    *,
    k: int = 60,
    limit: int = 20,
) -> list[int]:
    """여러 순위 목록을 Reciprocal Rank Fusion으로 한 순서로 합친다."""
    return [doc_id for doc_id, _score in reciprocal_rank_fusion_scored(rankings, k=k, limit=limit)]
