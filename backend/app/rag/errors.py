class GuideError(Exception):
    """가이드 검색이나 답변 생성이 실패했을 때."""


class GuideNotReady(GuideError):
    """인덱스나 재정렬 모델을 아직 쓸 수 없을 때."""
