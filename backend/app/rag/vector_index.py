from __future__ import annotations

from app.rag.errors import GuideNotReady


class VectorIndex:
    """코사인 유사도용 FAISS 인덱스.

    쪽 수가 적어도 정확도가 우선이라 근사 인덱스가 아니라 전수 내적 검색을 쓴다.
    벡터는 L2 정규화한 뒤 내적으로 코사인을 계산한다.
    """

    def __init__(self, matrix) -> None:
        try:
            import faiss
            import numpy as np
        except ImportError as exc:
            raise GuideNotReady("faiss-cpu가 설치되어 있지 않습니다.") from exc
        vectors = np.ascontiguousarray(matrix, dtype=np.float32)
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self._faiss = faiss
        self._index = index

    def ranked(self, vector, k: int) -> list[tuple[int, float]]:
        import numpy as np

        total = int(self._index.ntotal)
        if total == 0 or k <= 0:
            return []
        query = np.ascontiguousarray(vector, dtype=np.float32).reshape(1, -1)
        self._faiss.normalize_L2(query)
        scores, ids = self._index.search(query, min(k, total))
        return [
            (int(doc_id), float(score))
            for doc_id, score in zip(ids[0], scores[0], strict=True)
            if int(doc_id) >= 0
        ]

    def search(self, vector, k: int) -> list[int]:
        return [index for index, _score in self.ranked(vector, k)]
