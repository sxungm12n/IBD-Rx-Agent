from __future__ import annotations

from app.rag.config import chat_model, openai_api_key
from app.rag.errors import GuideError, GuideNotReady
from app.rag.types import Passage

_SYSTEM = """당신은 염증성장질환을 진료하는 소화기내과 전문의입니다.
답변의 근거는 오직 제공된 「2024 대한장연구학회 염증성장질환 보험가이드북」 발췌뿐입니다.

규칙
- 발췌에 있는 수치, 용량, 기간, 검사 기준, 급여 조건만 말합니다. 발췌에 없으면 그 사실을 밝히고 추측하지 않습니다.
- 환자를 진단하거나 발췌 밖의 처방을 권하지 않습니다. 급여 기준과 가이드북에 적힌 투여 원칙을 동료 의사에게 설명하듯 씁니다.
- 한국어로 씁니다. 마크다운 기호는 쓰지 않습니다.
- 문단 순서는 다음을 지킵니다.
  결론: 한두 문장
  기준: 해당하는 급여, 투여, 검사 조건
  근거: 사용한 페이지 번호
  확인: 발췌만으로 단정할 수 없는 점. 없으면 이 문단은 생략합니다.
- 마지막에 한 문장으로, 고시 원문과 환자 상태를 함께 확인해야 한다는 점을 적습니다."""

_ANSWER_ONLY = """당신은 2024 대한장연구학회 염증성장질환 보험가이드북 시험의 응시자입니다.
근거는 제공된 발췌뿐입니다. 발췌에 없는 수치, 조건, 금기는 만들지 않습니다.
출력은 답뿐입니다.
- 첫 줄은 반드시 "답: "으로 시작하고, 그 뒤에 핵심 답만 적습니다.
- 항목을 모두 쓰는 질문이면 "답:" 다음 줄부터 항목만 한 줄에 하나씩 적습니다.
- 인사, 근거, 페이지 번호, 설명 문장은 쓰지 않습니다.
- 발췌에 그 기준이 없으면 "답: 가이드북에 적혀 있지 않다"라고만 씁니다."""


# 평가용 답 형식 (answer_only일 때). short는 A·A2형(단답), case는 C형(환자 판정), drugs는 D형(약제 선택).
# STAGE1/eval_a.py의 기본 LLM 답 형식과 같은 문장을 쓴다.
_ANSWER_ONLY_BASE = """당신은 2024 대한장연구학회 염증성장질환 보험가이드북 시험의 응시자입니다.
근거는 제공된 발췌뿐입니다. 발췌에 없는 수치, 조건, 금기는 만들지 않습니다.
출력은 지정한 형식뿐입니다.
"""
_ANSWER_STYLE = {
    "case": _ANSWER_ONLY_BASE + """- 첫 줄은 "판정: " 뒤에 예, 아니오, 판단 불가 중 하나만 씁니다.
- 둘째 줄은 "이유: " 뒤에 판정을 가른 기준을 한두 문장으로 씁니다.
- 인사, 페이지 번호는 쓰지 않습니다.""",
    "drugs": _ANSWER_ONLY_BASE + """- 첫 줄은 "인정: " 뒤에 급여가 인정되는 약의 성분명을 쉼표로 나열합니다. 없으면 "인정: 없음"이라고 씁니다.
- 다음 줄부터 제외되는 약을 한 줄에 하나씩 "제외: 성분명 - 이유"로 씁니다. 후보 약은 모두 인정 또는 제외 중 한 곳에 씁니다.
- 인사, 페이지 번호는 쓰지 않습니다.""",
    "open_drugs": _ANSWER_ONLY_BASE + """- 첫 줄은 "인정: " 뒤에 급여로 쓸 수 있는 약의 성분명을 쉼표로 나열합니다. 없으면 "인정: 없음"이라고 씁니다.
- 둘째 줄은 "이유: " 뒤에 판단 근거를 한두 문장으로 씁니다.
- 인사, 페이지 번호는 쓰지 않습니다.""",
}


def _context(passages: list[Passage]) -> str:
    blocks: list[str] = []
    for index, passage in enumerate(passages, start=1):
        page = f"p.{passage.page}" if passage.page is not None else "페이지 없음"
        drugs = ", ".join(passage.drugs) or "없음"
        disease = ", ".join(passage.disease) or "없음"
        blocks.append(
            f"[{index}] {page} · {passage.section} · {passage.title}\n"
            f"약제: {drugs}\n질환: {disease}\n{passage.text}"
        )
    return "\n\n".join(blocks)


_PLAYBOOK = """

참고 노트
아래는 이전 문제를 풀며 정리한 답변 요령입니다. 답의 내용은 반드시 가이드북 발췌를 따르고, 노트가 발췌와 다르면 발췌를 따릅니다.
{playbook}"""


def generate_answer(
    question: str,
    passages: list[Passage],
    *,
    answer_only: bool = False,
    playbook: str | None = None,
    answer_style: str = "short",
) -> str:
    if not passages:
        if answer_only:
            return {"case": "판정: 판단 불가\n이유: 가이드북 발췌를 찾지 못함", "drugs": "인정: 없음", "open_drugs": "인정: 없음"}.get(
                answer_style, "답: 가이드북에 적혀 있지 않다"
            )
        return (
            "가이드북에서 이 질문과 맞는 원문을 찾지 못했습니다. "
            "약제명이나 질환명을 넣어 다시 물어봐 주세요."
        )
    key = openai_api_key()
    if not key:
        raise GuideNotReady("OPENAI_API_KEY가 없습니다.")
    try:
        from openai import OpenAI, OpenAIError
    except ImportError as exc:
        raise GuideNotReady("openai 패키지가 설치되어 있지 않습니다.") from exc

    user = f"질문:\n{question}\n\n가이드북 발췌:\n{_context(passages)}"
    system = _ANSWER_STYLE.get(answer_style, _ANSWER_ONLY) if answer_only else _SYSTEM
    if playbook and playbook.strip():
        system += _PLAYBOOK.replace("{playbook}", playbook.strip())
    # 평가 baseline과 같은 Responses API·기본 reasoning 설정을 쓴다. 추론 모델은 temperature를 받지 않는다.
    try:
        response = OpenAI(api_key=key).responses.create(
            model=chat_model(),
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except OpenAIError as exc:
        raise GuideError(f"답변 생성에 실패했습니다. {exc}") from exc

    text = (response.output_text or "").strip()
    if not text:
        raise GuideError("답변이 비어 있습니다.")
    return text
