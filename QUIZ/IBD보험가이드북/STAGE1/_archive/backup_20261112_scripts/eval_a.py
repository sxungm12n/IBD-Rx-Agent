#!/usr/bin/env python3
"""STAGE1 A형 평가: 문항(a_items.jsonl)을 평가 대상에 묻고, 코드 + LLM 채점자로 채점한다.

평가 대상 (--target)
  llm    검색 없는 모델. "2024 KASID 보험가이드북 기준으로 답하라"는 지시와 질문만 준다.
  agent  내 에이전트의 /api/chat. 질문만 보낸다 (정답·룰엔진 결과는 보내지 않는다).
  file   다른 곳에서 받은 답 파일(jsonl: {"id":..., "reply":...})을 채점만 한다.

두 대상 모두 질문 끝에 같은 답 형식 문장(ANSWER_FORMAT)을 붙인다. 채점자에게는 답 전체를 넘긴다.

채점
  LLM 채점자가 정답 + 채점 열쇠 + 답 전체를 보고 맞음/부분/틀림과 요소별 판정을 낸다. 최종 판정 = 채점자 판정.
  문항 유형마다 규칙 코드를 덧붙이지 않는다. 대신 human_check.csv('부분' 전부 + 나머지 무작위 20%)에
  사람 판정을 적어 채점자와의 일치도를 보고한다.

점수
  본 점수: 금기(G7) 6문항을 뺀 101문항. 맞음 1, 부분 0.5, 틀림 0.
  보조 점수: 금기 6문항(체크리스트 5 + MTX 금기 1)의 항목 재현율(맞힌 항목 / 전체 항목).
  같은 정답이 여러 약에 반복되므로 고유 정답 단위 점수도 낸다.

실행 예 (IBD보험가이드북 폴더에서)
  python3 STAGE1/eval_a.py --target llm --phase baseline --limit 5
  python3 STAGE1/eval_a.py --target llm --phase baseline   # gpt-5.6-terra 답만
  python3 STAGE1/eval_a.py --target llm --phase judge      # 저장된 답을 gpt-6-sol로 채점
  python3 STAGE1/eval_a.py --target llm                    # 답과 채점을 이어서
  python3 STAGE1/eval_a.py --target agent --agent-ping     # 에이전트 요청 형식 확인 (1문항)
  python3 STAGE1/eval_a.py --target agent
  python3 STAGE1/eval_a.py --target llm --report           # API 안 부르고 집계만

이미 답·채점이 저장된 문항은 다시 부르지 않는다(중단 후 이어 하기).
다시 하려면 --fresh. --phase judge --fresh는 채점만 지우고 받아 둔 답은 남긴다.
results.csv: 전 문항을 문제 · 정답 · 모델 답 · 일치 여부(일치/부분 일치/불일치)로 정리한 표.
human_overrides.csv(id, 채점자 판정, 사람 판정, 메모, 보정자)를 결과 폴더에 두면 채점자 판정은 그대로 두고
'사람 보정 반영' 점수를 따로 낸다. 채점 프롬프트는 고정한다.
llm 결과는 eval_out/llm_<모델>/ 에 쌓인다. 그 폴더에 다른 모델의 답이 있으면 멈춘다.
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as futures
import csv
import datetime as dt
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # IBD보험가이드북
DEFAULT_ITEMS = HERE / "output" / "a_items.jsonl"
OUT_ROOT = HERE / "eval_out"

ANSWER_FORMAT = (
    "\n\n[답만 쓸 것]\n"
    "2024 대한장연구학회 염증성장질환 보험가이드북의 급여 기준만으로 답하세요.\n"
    "- 첫 줄은 반드시 \"답: \"으로 시작하고, 그 뒤에 핵심 답만 적으세요.\n"
    "- 항목을 모두 쓰는 질문이면 \"답:\" 다음 줄부터 항목만 한 줄에 하나씩 적으세요.\n"
    "- 인사, 근거, 페이지 번호, 설명 문장은 쓰지 마세요.\n"
    "- 가이드북에 그 기준이 없으면 기준을 만들지 말고 \"답: 가이드북에 적혀 있지 않다\"라고만 쓰세요."
)
LLM_SYSTEM = (
    "당신은 2024 대한장연구학회 염증성장질환 보험가이드북 시험의 응시자입니다. "
    "가이드북 본문은 주어지지 않습니다. 그 가이드북에 적힌 급여·투여·검사 기준만 사용하고, "
    "진단·용량 제안·논문·병원 관행은 덧붙이지 않습니다. 출력은 답뿐이며 다른 문장은 쓰지 않습니다."
)

DEFAULTS = {
    "EVAL_TARGET_MODEL": "gpt-5.6-terra",  # 검색 없는 baseline. 에이전트와 같게 두면 검색의 기여를 볼 수 있다
    "EVAL_JUDGE_MODEL": "gpt-6-sol",       # baseline과 다른 채점 모델
    "AGENT_URL": "",
}


# ---------------------------------------------------------------- 설정·키


def load_env() -> dict:
    """IBD보험가이드북/.env, STAGE1/.env 순으로 읽는다. .env 값이 셸 환경변수보다 우선한다."""
    env = dict(DEFAULTS)
    for key in env:
        if os.environ.get(key):
            env[key] = os.environ[key]
    env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
    env["_key_source"] = "셸 환경변수" if env["OPENAI_API_KEY"] else ""
    # STAGE1 → IBD보험가이드북 → QUIZ → 프로젝트. 키가 비어 있을 때만 RAG .env를 채운다.
    rag_env = HERE.parents[2] / "data" / "RAG" / ".env"
    for path in (ROOT / ".env", HERE / ".env", rag_env):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            if not value:
                continue
            name = key.strip()
            if name == "OPENAI_API_KEY" and env.get("OPENAI_API_KEY") and path == rag_env:
                continue
            env[name] = value
            if name == "OPENAI_API_KEY":
                env["_key_source"] = "data/RAG/.env" if path == rag_env else str(path.relative_to(ROOT))
    return env


def describe_key(env: dict) -> str:
    key = env.get("OPENAI_API_KEY", "")
    if not key:
        return "OPENAI_API_KEY 없음"
    return f"OPENAI_API_KEY: {env['_key_source']}, 길이 {len(key)}, 끝 4자리 …{key[-4:]}"


# ---------------------------------------------------------------- HTTP


class CallError(Exception):
    pass


def post_json(url: str, payload: dict, headers: dict, timeout: int = 180, retries: int = 4) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            if error.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** attempt + random.random())
                continue
            if error.code == 401:
                raise CallError("401: API 키가 틀렸거나 권한이 없음 (.env의 OPENAI_API_KEY 확인)") from None
            raise CallError(f"HTTP {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < retries:
                time.sleep(2 ** attempt + random.random())
                continue
            raise CallError(f"연결 실패: {error}") from None
    raise CallError("재시도 초과")


def openai_text(env: dict, model: str, system: str, user: str, schema: dict | None = None) -> str:
    if not env.get("OPENAI_API_KEY"):
        raise CallError("OPENAI_API_KEY가 없음 (.env에 넣기)")
    payload = {
        "model": model,
        "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if schema:
        payload["text"] = {"format": {"type": "json_schema", "name": "grade", "schema": schema, "strict": True}}
    data = post_json("https://api.openai.com/v1/responses", payload, {"Authorization": f"Bearer {env['OPENAI_API_KEY']}"})
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    texts = [
        part.get("text", "")
        for item in data.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") in ("output_text", "text")
    ]
    if not texts:
        raise CallError(f"응답에 텍스트가 없음: {str(data)[:200]}")
    return "".join(texts)


# ---------------------------------------------------------------- 평가 대상


def ask_llm(env: dict, item: dict) -> str:
    user = (
        "2024 대한장연구학회 염증성장질환 보험가이드북의 기준으로 답하세요. 답만 말하세요.\n\n"
        f"문제: {item['question']}"
        f"{ANSWER_FORMAT}"
    )
    return openai_text(env, env["EVAL_TARGET_MODEL"], LLM_SYSTEM, user)


def agent_payload(template: dict, message: str):
    """템플릿 안의 문자열 '{question}'을 질문으로 바꾼다."""
    if isinstance(template, dict):
        return {k: agent_payload(v, message) for k, v in template.items()}
    if isinstance(template, list):
        return [agent_payload(v, message) for v in template]
    if isinstance(template, str):
        return template.replace("{question}", message)
    return template


def dig(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def agent_message(template: dict, item: dict) -> str:
    """answer_only면 검색용으로 문제만 보낸다. 답 형식은 에이전트 프롬프트가 맡는다."""
    message = item["question"]
    if not (isinstance(template, dict) and template.get("answer_only")):
        message += ANSWER_FORMAT
    return message


def ask_agent(env: dict, item: dict, template: dict, reply_key: str) -> tuple[str, dict]:
    """답 문자열과 응답 전체(출처 필드 포함)를 함께 돌려준다."""
    url = env["AGENT_URL"].rstrip("/")
    if not url:
        raise CallError("에이전트 주소가 없음: --agent-url 또는 .env의 AGENT_URL")
    data = post_json(url, agent_payload(template, agent_message(template, item)), {})
    try:
        reply = dig(data, reply_key)
    except (KeyError, IndexError, TypeError):
        raise CallError(f"응답에 '{reply_key}'가 없음. 응답 키: {list(data)[:10]}") from None
    if not isinstance(reply, str) or not reply.strip():
        raise CallError("에이전트 답이 비어 있음")
    return reply, data


# ---------------------------------------------------------------- 답 형식 확인 (채점에는 쓰지 않음)


ANSWER_LINE = re.compile(r"^[ \t>*#-]*\**[ \t]*답[ \t]*\**[ \t]*[:：]", flags=re.M)
NOT_WRITTEN = re.compile(r"적혀\s*있지\s*않|명시(되어\s*있지\s*않|하지\s*않)|언급(이|되어)\s*(없|있지\s*않)")
ONLY_NO = re.compile(r"\s*(없(다|음|습니다)|해당\s*(사항\s*)?없(다|음))\.?\s*")


def answer_body(reply: str) -> str:
    """'답:' 머리말만 떼어 낸 본문. '없다'로 답한 수를 셀 때만 쓴다."""
    return ANSWER_LINE.sub("", reply.replace("\r\n", "\n"), count=1).strip()


# ---------------------------------------------------------------- LLM 채점


JUDGE_SYSTEM = """당신은 IBD 보험급여 퀴즈의 채점자입니다. 문제의 정답과 채점 열쇠를 기준으로 답을 채점합니다. 급여 기준을 스스로 다시 판단하지 마세요.

규칙
- 표현이 달라도 뜻이 같으면 맞음. 영문·한글, 동의어(스테로이드=코르티코스테로이드, 6-MP=6-머캅토퓨린, 아자티오프린=Azathioprine, 면역억제제=면역조절제), 단위 환산(1×10⁹/L = 1,000 cells/mm³)은 같은 것으로 봅니다.
- 숫자, 이상/초과, 그리고/또는이 정답과 다르면 그 요소는 틀림입니다.
- 정답에 없는 조건을 지어내 뜻이 바뀌면 틀림. 맞는 답에 덧붙인 설명은 감점하지 않습니다.
- 정답이 "가이드북에 적혀 있지 않다"인 문항: "없다", "해당 없음", "명시되어 있지 않다"도 맞음. 기준을 지어내면 틀림.
- 채점 열쇠의 "함께 써도 정답"은 써도 맞고 안 써도 맞습니다. "참고(필수 아님)"는 채점하지 않습니다.
- 이전 치료 문항은 필수 요소 3개로 봅니다: (1) 최소 가지 수(열쇠에 2가 있으면 "2가지 이상"이 있어야 함, 없음(null)이면 요구하지 않음) (2) 치료 종류(열쇠 목록의 절반 이상을 언급) (3) 반응 조항(열쇠의 조항을 모두: 반응 없음 / 불내성(내약성 없음) / 금기 / 부작용 중단). 3개 모두 맞으면 맞음, 1~2개면 부분, 0개면 틀림.
- 목록 문항(형식=목록)은 정답 항목마다 답에 같은 뜻의 항목이 있는지 보고 '맞힌 항목 수'를 세고, 정답에 없는 항목(임상적으로 맞는 말이어도 가이드북 정답에 없으면 포함)은 '정답에 없는 항목 수'로 셉니다. 정답에 없는 항목이 하나라도 있으면 틀림. 없으면: 모두 맞히면 맞음, 일부만 맞히면 부분, 하나도 못 맞히면 틀림. 목록이 아닌 문항은 두 수를 0으로 둡니다.
- 그 밖의 문항: 정답의 요소를 모두 맞히면 맞음, 일부만 맞히면 부분, 핵심 요소(척도·값·비교·결합)가 틀리거나 없으면 틀림.
"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "판정": {"type": "string", "enum": ["맞음", "부분", "틀림"]},
        "요소": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"요소": {"type": "string"}, "맞음": {"type": "boolean"}},
                "required": ["요소", "맞음"],
                "additionalProperties": False,
            },
        },
        "맞힌 항목 수": {"type": "integer"},
        "정답에 없는 항목 수": {"type": "integer"},
        "이유": {"type": "string"},
    },
    "required": ["판정", "요소", "맞힌 항목 수", "정답에 없는 항목 수", "이유"],
    "additionalProperties": False,
}


def judge_llm(env: dict, item: dict, answer: str) -> dict:
    gold = item["answer"]
    user = json.dumps(
        {
            "질문": item["question"],
            "정답": gold["정답"],
            "형식": gold["형식"],
            "채점 열쇠": gold["채점"],
            "채점할 답": answer,
        },
        ensure_ascii=False,
        indent=1,
    )
    text = openai_text(env, env["EVAL_JUDGE_MODEL"], JUDGE_SYSTEM, user, schema=JUDGE_SCHEMA)
    result = json.loads(text)
    if result.get("판정") not in ("맞음", "부분", "틀림"):
        raise CallError(f"채점 결과 형식 오류: {text[:200]}")
    return result


# ---------------------------------------------------------------- 실행


SCORE = {"맞음": 1.0, "부분": 0.5, "틀림": 0.0}


def is_checklist(item: dict) -> bool:
    """보조 점수로 빼는 문항: 금기(G7) 6문항 = 투여 전 체크리스트 5 + MTX 금기 목록 1. 모두 목록형·허가사항."""
    return item["gate"] == "G7"


def finalize(item: dict, record: dict) -> dict:
    record["최종"] = record["LLM"]["판정"]
    if is_checklist(item):
        total = len(item["answer"]["정답"])
        record["항목 재현율"] = round(min(record["LLM"].get("맞힌 항목 수", 0), total) / total, 4)
        record["정답에 없는 항목 수"] = record["LLM"].get("정답에 없는 항목 수", 0)
    return record


def load_jsonl(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = row
    return out


def append_jsonl(path: Path, row: dict, lock: threading.Lock) -> None:
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def rewrite_jsonl(path: Path, rows: dict) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()), encoding="utf-8")


def summarize(items: list[dict], graded: dict, meta: dict) -> dict:
    main = [i for i in items if not is_checklist(i)]
    aux = [i for i in items if is_checklist(i)]

    def score(group):
        done = [graded[i["id"]] for i in group if graded.get(i["id"], {}).get("최종")]
        if not done:
            return {"문항": len(group), "채점됨": 0}
        counts = collections.Counter(r["최종"] for r in done)
        return {
            "문항": len(group),
            "채점됨": len(done),
            "점수": round(sum(SCORE[r["최종"]] for r in done) / len(done), 4),
            "완전 정답률": round(counts["맞음"] / len(done), 4),
            "맞음": counts["맞음"],
            "부분": counts["부분"],
            "틀림": counts["틀림"],
        }

    by_gate = collections.defaultdict(list)
    by_class = collections.defaultdict(list)
    unique = collections.defaultdict(list)
    for item in main:
        by_gate[item["기준"].split("(")[0]].append(item)
        by_class[item.get("drug_class") or "?"].append(item)
        gold = item["answer"]["정답"]
        unique[(item["기준"], json.dumps(gold, ensure_ascii=False))].append(item)

    unique_scores = []
    for group in unique.values():
        done = [SCORE[graded[i["id"]]["최종"]] for i in group if graded.get(i["id"], {}).get("최종")]
        if done:
            unique_scores.append(sum(done) / len(done))

    contrast = [
        i for i in main
        if "적혀 있지 않다" in json.dumps(i["answer"]["정답"], ensure_ascii=False)
    ]
    abstained = [
        i for i in main
        if i not in contrast and graded.get(i["id"], {}).get("최종")
        and (NOT_WRITTEN.search(answer_body(graded[i["id"]]["채점 대상"]))
             or ONLY_NO.fullmatch(answer_body(graded[i["id"]]["채점 대상"])))
    ]
    recalls = [graded[i["id"]]["항목 재현율"] for i in aux if "항목 재현율" in graded.get(i["id"], {})]
    extras = [graded[i["id"]].get("정답에 없는 항목 수", 0) for i in aux if "항목 재현율" in graded.get(i["id"], {})]
    no_answer_line = [r["id"] for r in graded.values() if r.get("답 줄 있음") is False]
    return {
        **meta,
        "본 점수 (금기 6문항 제외)": score(main),
        "고유 정답 단위 점수": {"고유 정답 수": len(unique), "채점됨": len(unique_scores),
                          "점수": round(sum(unique_scores) / len(unique_scores), 4) if unique_scores else None},
        "기준별": {k: score(v) for k, v in by_gate.items()},
        "약 계열별": {k: score(v) for k, v in by_class.items()},
        "대조 문항 ('적혀 있지 않다')": score(contrast),
        "기준 있는 문항에서 '없다'로 답한 수": len(abstained),
        "보조: 금기 항목 재현율": {"문항": len(aux), "채점됨": len(recalls),
                                "평균": round(sum(recalls) / len(recalls), 4) if recalls else None,
                                "정답에 없는 항목 수(합)": sum(extras)},
        "'답:' 줄 없는 답": no_answer_line,
    }


def write_review(path: Path, items: list[dict], graded: dict, sample_rate: float, seed: int) -> int:
    """사람 확인용: '부분' 판정 전부 + 나머지에서 무작위 표본. 채점자 신뢰도(사람 vs 채점자 일치도)에 쓴다."""
    rng = random.Random(seed)
    done = [i for i in items if graded.get(i["id"], {}).get("최종")]
    chosen = {i["id"] for i in done if graded[i["id"]]["최종"] == "부분"}
    rest = [i for i in done if i["id"] not in chosen]
    chosen |= {i["id"] for i in rng.sample(rest, k=min(len(rest), round(len(done) * sample_rate)))}
    columns = ["id", "기준", "질문", "정답", "모델 답", "채점자 판정", "채점자 이유", "사람 판정(맞음/부분/틀림)", "코멘트"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in items:
            if item["id"] not in chosen:
                continue
            r = graded[item["id"]]
            gold = item["answer"]["정답"]
            writer.writerow({
                "id": item["id"], "기준": item["기준"], "질문": item["question"],
                "정답": " / ".join(gold) if isinstance(gold, list) else gold,
                "모델 답": answer_body(r["채점 대상"]), "채점자 판정": r["최종"], "채점자 이유": r["LLM"].get("이유", ""),
                "사람 판정(맞음/부분/틀림)": "", "코멘트": "",
            })
    return len(chosen)


MATCH = {"맞음": "일치", "부분": "부분 일치", "틀림": "불일치"}
OVERRIDE_COLUMNS = ["id", "채점자 판정", "사람 판정", "메모", "보정자"]


def load_overrides(path: Path) -> dict:
    """사람 보정 파일(human_overrides.csv). '사람 판정'이 맞음/부분/틀림인 행만 쓴다. 채점자 판정은 그대로 두고 따로 집계한다."""
    if not path.exists():
        return {}
    rows = csv.DictReader(path.open(encoding="utf-8-sig"))
    return {r["id"]: r for r in rows if (r.get("사람 판정") or "").strip() in SCORE}


def apply_overrides(graded: dict, overrides: dict) -> dict:
    return {k: (dict(v, 최종=overrides[k]["사람 판정"].strip()) if k in overrides else v) for k, v in graded.items()}



def write_results(path: Path, items: list[dict], graded: dict, answers: dict, overrides: dict | None = None) -> int:
    """사람이 한눈에 보는 표: 문제 - 정답 - 모델 답 - 일치/불일치 (전 문항, 엑셀로 열림). 사람 보정이 있으면 함께 적는다."""
    overrides = overrides or {}
    columns = ["id", "기준", "문제", "정답", "모델 답", "일치 여부", "채점자 이유", "사람 보정", "보정 메모", "최종 (보정 반영)", "점수 구분"]
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in items:
            if item["id"] not in answers:
                continue
            r = graded.get(item["id"], {})
            gold = item["answer"]["정답"]
            reply = answer_body(answers[item["id"]]["reply"])
            writer.writerow({
                "id": item["id"], "기준": item["기준"], "문제": item["question"],
                "정답": " / ".join(gold) if isinstance(gold, list) else gold,
                "모델 답": " / ".join(line.strip(" -•·") for line in reply.splitlines() if line.strip()),
                "일치 여부": MATCH.get(r.get("최종"), "채점 전"),
                "채점자 이유": (r.get("LLM") or {}).get("이유", ""),
                "사람 보정": MATCH.get(overrides.get(item["id"], {}).get("사람 판정", "").strip(), ""),
                "보정 메모": overrides.get(item["id"], {}).get("메모", ""),
                "최종 (보정 반영)": MATCH.get((overrides.get(item["id"], {}).get("사람 판정") or r.get("최종") or "").strip(), "채점 전"),
                "점수 구분": (f"보조(금기 재현율 {r.get('항목 재현율', '')}, 정답에 없는 항목 {r.get('정답에 없는 항목 수', '')}개)"
                             if is_checklist(item) else "본 점수"),
            })
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="STAGE1 A형 평가")
    parser.add_argument("--target", choices=["llm", "agent", "file"], required=True)
    parser.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    parser.add_argument("--answers", type=Path, help="--target file: {id, reply} jsonl")
    parser.add_argument("--run", help="결과 폴더 이름 (기본: 대상 이름)")
    parser.add_argument("--phase", choices=["baseline", "judge", "all"], default="all",
                        help="baseline은 답만 받고, judge는 저장된 답을 채점하고, all은 둘 다")
    parser.add_argument("--limit", type=int, help="앞에서 N문항만")
    parser.add_argument("--only", help="이 기준만 (예: 활성도)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fresh", action="store_true", help="저장된 답·채점을 지우고 처음부터")
    parser.add_argument("--report", action="store_true", help="API를 부르지 않고 집계만")
    parser.add_argument("--agent-url", help="에이전트 /api/chat 주소 (또는 .env의 AGENT_URL)")
    parser.add_argument("--agent-payload", type=Path, default=HERE / "agent_payload.json",
                        help="요청 본문 템플릿. 문자열 '{question}'이 질문으로 바뀐다")
    parser.add_argument("--agent-reply-key", default="reply", help="응답 JSON에서 답이 든 키 (점으로 경로: data.reply)")
    parser.add_argument("--agent-ping", action="store_true", help="1문항만 보내고 응답 모양을 보여 줌")
    parser.add_argument("--review-rate", type=float, default=0.2, help="사람 확인 표본 비율 ('부분'은 전부)")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    env = load_env()
    if args.agent_url:
        env["AGENT_URL"] = args.agent_url
    items = [json.loads(line) for line in args.items.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.only:
        items = [i for i in items if i["기준"].startswith(args.only)]
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("문항이 없음", file=sys.stderr)
        return 1

    template = {}
    if args.target == "agent":
        if not args.agent_payload.exists():
            print(f"요청 템플릿이 없음: {args.agent_payload}", file=sys.stderr)
            return 1
        template = json.loads(args.agent_payload.read_text(encoding="utf-8"))
        if args.agent_ping:
            if not env.get("AGENT_URL"):
                print("에이전트 주소가 없음: --agent-url 또는 .env의 AGENT_URL", file=sys.stderr)
                return 1
            item = items[0]
            body = agent_payload(template, agent_message(template, item))
            print("보낸 본문:", json.dumps(body, ensure_ascii=False)[:500])
            data = post_json(env["AGENT_URL"].rstrip("/"), body, {})
            print("응답 키:", list(data) if isinstance(data, dict) else type(data).__name__)
            try:
                reply = dig(data, args.agent_reply_key)
                print(f"'{args.agent_reply_key}' 앞부분:", str(reply)[:400])
            except (KeyError, IndexError, TypeError):
                print(f"'{args.agent_reply_key}' 키가 없음 → --agent-reply-key로 맞추기")
            return 0

    need_key = not args.report and (
        (args.phase != "judge" and args.target == "llm") or args.phase != "baseline"
    )
    if need_key and not env.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY가 없음: IBD보험가이드북/.env에 넣기 (env.example 참고)", file=sys.stderr)
        return 1
    if not args.report and args.phase != "judge" and args.target == "agent" and not env.get("AGENT_URL"):
        print("에이전트 주소가 없음: --agent-url 또는 .env의 AGENT_URL", file=sys.stderr)
        return 1

    run = args.run or (args.target if args.target != "llm"
                       else "llm_" + re.sub(r"[^\w.-]+", "_", env["EVAL_TARGET_MODEL"]))
    out = OUT_ROOT / run
    out.mkdir(parents=True, exist_ok=True)
    answers_path, graded_path = out / "answers.jsonl", out / "graded.jsonl"
    answers = load_jsonl(answers_path)
    if args.target == "llm":
        others = {row.get("대상") for row in answers.values()} - {env["EVAL_TARGET_MODEL"]}
        if others:
            print(f"이 폴더의 답은 {others} 모델 것임. --run으로 다른 폴더를 쓰세요.", file=sys.stderr)
            return 1
    if args.fresh:
        targets = [graded_path] if args.phase == "judge" else [answers_path, graded_path]
        for path in targets:
            if path.exists():
                path.unlink()
        if args.phase != "judge":
            answers = {}

    lock = threading.Lock()
    graded = {} if args.fresh else load_jsonl(graded_path)
    print(f"[{run}] 문항 {len(items)} / 저장된 답 {len(answers)} / 저장된 채점 {len(graded)}")
    uses_target = not args.report and args.phase != "judge" and args.target == "llm"
    uses_judge = not args.report and args.phase != "baseline"
    if uses_target or uses_judge:
        print(describe_key(env))
        asked = env["EVAL_TARGET_MODEL"] if args.target == "llm" else args.target
        graded_by = env["EVAL_JUDGE_MODEL"]
        print(f"단계: {args.phase} / 평가 대상: {asked} / 채점: {graded_by if args.phase != 'baseline' else '아직 안 함'}")

    # 1) 답 받기
    if not args.report and args.phase != "judge":
        if args.target == "file":
            if not args.answers:
                print("--target file에는 --answers가 필요", file=sys.stderr)
                return 1
            for row in load_jsonl(args.answers).values():
                if row["id"] not in answers:
                    answers[row["id"]] = {"id": row["id"], "reply": row["reply"], "대상": "file"}
            rewrite_jsonl(answers_path, answers)
        else:
            todo = [i for i in items if i["id"] not in answers]

            def fetch(item):
                started = time.time()
                raw = None
                if args.target == "llm":
                    reply = ask_llm(env, item)
                    subject = env["EVAL_TARGET_MODEL"]
                else:
                    reply, raw = ask_agent(env, item, template, args.agent_reply_key)
                    subject = env["AGENT_URL"]
                row = {"id": item["id"], "reply": reply, "대상": subject,
                       "초": round(time.time() - started, 1), "시각": dt.datetime.now().isoformat(timespec="seconds")}
                if raw is not None:
                    row["응답"] = raw
                append_jsonl(answers_path, row, lock)
                return row

            errors = run_pool(fetch, todo, args.workers, "답")
            answers = load_jsonl(answers_path)
            if errors:
                print(f"답을 못 받은 문항 {len(errors)}개 (다시 실행하면 이어서 함): {errors[:3]}")

    if args.phase == "baseline" and not args.report:
        got = sum(1 for item in items if item["id"] in answers)
        print(f"baseline 답 {got}/{len(items)}개 저장 → {answers_path}")
        print(f"채점은 답이 다 모인 뒤: python3 STAGE1/eval_a.py --target {args.target} --phase judge --run {run}")
        return 0 if got == len(items) else 1

    missing_answers = [item["id"] for item in items if item["id"] not in answers]
    if args.phase == "judge" and missing_answers and not args.report:
        print(f"저장된 baseline 답이 없는 문항 {len(missing_answers)}개. 먼저 --target {args.target} --phase baseline --run {run} 을 실행하세요.", file=sys.stderr)
        print("예:", ", ".join(missing_answers[:5]), file=sys.stderr)
        return 1

    # 2) 채점
    if not args.report and args.phase != "baseline":
        # 예전 형식(코드 채점이 섞인) 기록은 다시 채점한다
        todo = [i for i in items if i["id"] in answers
                and (i["id"] not in graded or not graded[i["id"]].get("LLM") or "코드" in graded[i["id"]]
                     or "정답에 없는 항목 수" not in graded[i["id"]]["LLM"])]

        def grade(item):
            reply = answers[item["id"]]["reply"].strip()
            record = {"id": item["id"], "채점 대상": reply, "답 줄 있음": bool(ANSWER_LINE.search(reply)),
                      "LLM": judge_llm(env, item, reply), "채점 모델": env["EVAL_JUDGE_MODEL"]}
            return finalize(item, record)

        results = {}

        def grade_and_keep(item):
            results[item["id"]] = grade(item)

        errors = run_pool(grade_and_keep, todo, args.workers, "채점")
        graded.update(results)
        rewrite_jsonl(graded_path, graded)
        if errors:
            print(f"채점 못 한 문항 {len(errors)}개: {errors[:3]}")

    # 3) 집계
    recorded = sorted({row.get("대상") for row in answers.values() if row.get("대상")})
    recorded_model = recorded[0] if len(recorded) == 1 else (recorded or None)
    meta = {
        "실행": run,
        "평가 대상": args.target,
        "평가 대상 모델": recorded_model if args.target == "llm" else None,
        "에이전트": recorded_model if args.target == "agent" else None,
        "채점": "LLM 채점자",
        "채점 모델": sorted({r.get("채점 모델") for r in graded.values() if r.get("채점 모델")}) or None,
        "문항 파일": str(args.items),
        "집계 시각": dt.datetime.now().isoformat(timespec="seconds"),
    }
    summary = summarize(items, graded, meta)
    overrides = load_overrides(out / "human_overrides.csv")
    if overrides:
        fixed = summarize(items, apply_overrides(graded, overrides), {})
        summary["사람 보정 반영"] = {
            "설명": "채점자 판정은 위에 그대로 두고, human_overrides.csv의 사람 판정으로 바꾼 결과",
            "보정 문항 수": len(overrides),
            "보정 목록": {k: f"{v.get('채점자 판정', '')} → {v['사람 판정'].strip()}" for k, v in overrides.items()},
            **{k: fixed[k] for k in ("본 점수 (금기 6문항 제외)", "고유 정답 단위 점수", "기준별", "약 계열별",
                                    "대조 문항 ('적혀 있지 않다')")},
        }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    picked = write_review(out / "human_check.csv", items, graded, args.review_rate, args.seed)
    shown = write_results(out / "results.csv", items, graded, answers, overrides)

    main_score = summary["본 점수 (금기 6문항 제외)"]
    print(f"본 점수: {main_score.get('점수')} (채점 {main_score['채점됨']}/{main_score['문항']}, 맞음 {main_score.get('맞음', 0)} · 부분 {main_score.get('부분', 0)} · 틀림 {main_score.get('틀림', 0)})")
    contrast = summary["대조 문항 ('적혀 있지 않다')"].get("점수")
    print(f"고유 정답 단위: {summary['고유 정답 단위 점수']['점수']} / 대조 문항: {contrast} / 금기 항목 재현율: {summary['보조: 금기 항목 재현율']['평균']}")
    if overrides:
        fixed_main = summary["사람 보정 반영"]["본 점수 (금기 6문항 제외)"]
        print(f"사람 보정 반영 ({len(overrides)}문항): 점수 {fixed_main.get('점수')}, 완전 정답률 {fixed_main.get('완전 정답률')}"
              f" (맞음 {fixed_main.get('맞음', 0)} · 부분 {fixed_main.get('부분', 0)} · 틀림 {fixed_main.get('틀림', 0)})")
    abstain_key = "기준 있는 문항에서 '없다'로 답한 수"
    print(f"{abstain_key}: {summary[abstain_key]}")
    for gate, value in summary["기준별"].items():
        print(f"  {gate}: {value.get('점수')} ({value['채점됨']}/{value['문항']})")
    missing_line = summary["'답:' 줄 없는 답"]
    if missing_line:
        print(f"'답:' 줄이 없는 답 {len(missing_line)}개 (형식만 어긋남, 채점은 답 전체로 함)")
    print(f"한눈에 보기 → {out / 'results.csv'} ({shown}문항: 문제·정답·모델 답·일치 여부)")
    print(f"결과 → {out}/ (answers.jsonl, graded.jsonl, summary.json, human_check.csv: {picked}문항)")
    return 0


def run_pool(fn, todo: list, workers: int, label: str) -> list[str]:
    if not todo:
        return []
    errors, done = [], 0
    with futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        jobs = {pool.submit(fn, item): item["id"] for item in todo}
        for job in futures.as_completed(jobs):
            done += 1
            try:
                job.result()
            except CallError as error:
                errors.append(f"{jobs[job]}: {error}")
                if "401" in str(error) or "OPENAI_API_KEY가 없음" in str(error) or "주소가 없음" in str(error):
                    for other in jobs:
                        other.cancel()
                    print(f"중단: {error}", file=sys.stderr)
                    break
            if done % 10 == 0 or done == len(todo):
                print(f"  {label} {done}/{len(todo)}", flush=True)
    return errors


if __name__ == "__main__":
    sys.exit(main())
