#!/usr/bin/env python3
"""선생–학생 검토·재검색 루프 (설계: TEACHER_LOOP_PLAN.md, 2026-11-20).

학생(gpt-5.6-terra)이 가이드북 발췌로 답하면, 선생이 답과 발췌를 대조해 '통과 / 다시 읽어 / 더 찾아'로 판정하고
부족한 부분과 찾아볼 곳만 조언한다. '더 찾아'면 코드가 그 쪽을 가이드북에서 찾아 붙이고, 학생이 다시 답한다. 최대 2회.

조건 (--arm)
  self   선생 = gpt-5.6-terra (자기 검토)            OpenAI Batch               폴더·실행 이름 self-g
  opus   선생 = claude-opus-5-5 (강한 선생)          Anthropic Message Batches  폴더·실행 이름 opus-g
  선생은 일반 지시문(TEACHER_TAG "g", 2026-11-23)을 쓴다. 2026-11-20 파일럿의 맞춤 지시문 결과는 self_pilot·opus_pilot.
  reask  선생 없음. 쪽도 붙이지 않고 같은 발췌·같은 지시문으로 학생이 한 번 더 답함 (다시 묻기만 대조군)
  route  선생 없음. 규칙 B(질문의 약·질환 → 고시·체크리스트·투약간격 쪽)로 쪽을 한 번 붙이고 학생이 한 번 답함
학생은 세 조건 모두 gpt-5.6-terra (OpenAI Batch). 0회차 학생 답은 기존 에이전트 답(eval_out/<유형>_agent_gpt-5.6-terra)을 재사용.

사용 (STAGE1에서, .venv_rag)
  .venv_rag/bin/python teacher_loop.py init   --arm opus [--pilot 5]   # 상태 만들기 (무료). --pilot N: 유형마다 N문항 (시드 고정)
  .venv_rag/bin/python teacher_loop.py next   --arm opus               # 할 일을 진행: 쪽 찾기(코드)·다음 배치 요청 파일 만들기 (무료)
  .venv_rag/bin/python teacher_loop.py submit --arm opus --yes         # 만든 배치 제출 (과금)
  .venv_rag/bin/python teacher_loop.py status --arm opus               # 진행 확인 (무료)
  .venv_rag/bin/python teacher_loop.py fetch  --arm opus               # 결과 받아 상태에 반영 (무료)
  … next → submit → fetch 를 '할 일 없음'이 나올 때까지 반복 …
  .venv_rag/bin/python teacher_loop.py finalize --arm opus             # 최종 답 → eval_out/<유형>_loop-<arm>_gpt-5.6-terra/answers.jsonl
  .venv_rag/bin/python teacher_loop.py report   --arm opus             # 판정 분포·누설 의심·추가 쪽·회차 (무료)
그다음 채점: C·D형 score_cases.py, A·A2형 regrade_v2_batch.py (기존과 같음).

상태: eval_out/teacher_loop/<이름>[_pilot]/state.jsonl (문항별), meta.json, batches/<번호>_<teacher|student>_r<회차>/
"""
import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "backend"))
import eval_a as E  # noqa: E402
from app.rag.generate import _ANSWER_ONLY, _ANSWER_STYLE, _context  # noqa: E402  (에이전트와 같은 지시문·발췌 형식)
from app.rag.types import Passage  # noqa: E402

OUT, EV = HERE / "output", HERE / "eval_out"
ROOT = EV / "teacher_loop"
CORPUS = HERE.parents[2] / "data" / "RAG" / "IBD_insurance_guide_2024.jsonl"
A_BACKUP = OUT / "_backup_20261110" / "a_items.jsonl"
TYPES = {"A": "a_items.jsonl", "A2": "a2_items.jsonl", "C": "c_items.jsonl", "D": "d_items.jsonl"}
RUN_PREFIX = {"A": "", "A2": "a2_", "C": "c_", "D": "d_"}
GRADED = {"A": "graded_v21.jsonl", "A2": "graded_v21.jsonl", "C": "graded_code.jsonl", "D": "graded_code.jsonl"}
FORMAT_NAME = {"A": "단답 (첫 줄 '답:')", "A2": "단답 (첫 줄 '답:')", "C": "환자 판정 ('판정:' 예/아니오/판단 불가 + '이유:')",
               "D": "보기 없는 약 선택 ('인정:' 성분명 목록 + '이유:')"}
STUDENT_MODEL = "gpt-5.6-terra"
# 학생 모델 (--student). qwen: 로컬 Qwen3-14B (GPU 서버 vLLM bf16 또는 Mac MLX). 요청 파일을 만들면 run_local_batch.py가 답을 채운다.
# 0회차 답은 그 모델의 기존 PDF 에이전트 답(agent_<라벨>), 상태 폴더는 eval_out/teacher_loop_<라벨>/, 결과 폴더는 …_<라벨>.
STUDENTS = {"gpt": ("openai", "gpt-5.6-terra", "gpt-5.6-terra"), "qwen": ("local", "Qwen/Qwen3-14B", "qwen3-14b-bf16")}
STUDENT = "gpt"         # main()에서 --student로 정함


def student_label() -> str:
    return STUDENTS[STUDENT][2]


def teacher_of(arm: str) -> tuple[str, str]:
    """self 선생 = 학생과 같은 모델 (qwen 학생이면 로컬 Qwen). opus 선생은 그대로 Claude Opus."""
    if arm == "self" and STUDENT != "gpt":
        return STUDENTS[STUDENT][0], STUDENTS[STUDENT][1]
    return TEACHERS[arm]
TEACHERS = {"self": ("openai", "gpt-5.6-terra"), "opus": ("anthropic", "claude-opus-5-5")}
ARMS = ["self", "opus", "route", "reask"]
NO_TEACHER = ("route", "reask")   # 선생 없이 학생이 한 번 다시 답함 (reask: 쪽도 안 붙임 = 다시 묻기만 대조군)
MAX_ROUNDS = 2          # 학생이 고쳐 쓰는 최대 횟수
PER_REQUEST = 2         # 찾기 요청 하나에 붙이는 최대 발췌 수
PER_ROUND = 4           # 한 회차에 붙이는 최대 발췌 수
OPUS_EFFORT, OPUS_MAX_TOKENS = "medium", 16000
# 100만 토큰당 달러 (정가, 입력·출력). 배치는 절반.
# gpt-5.6-terra: OpenAI 가격표 2026-07-30 인하 후 $2/$12 (배치 $1/$6, 272K 토큰 넘는 입력은 장문 단가). 2026-11-20 확인.
PRICE = {"claude-opus-5-5": (4.0, 20.0), "gpt-5.6-terra": (2.0, 12.0)}
# 비용 추정용 (2026-11-20 실측): 한국어 요청 글자당 입력 토큰. claude_batch/full 1,695,177토큰/1,934,188자,
# openai_batch/judge_claude_opus55_k0 1,587,947토큰/2,600,693자 (gpt-6-sol 토크나이저로 잰 값을 gpt-5.6-terra에도 씀)
TOKENS_PER_CHAR = {"anthropic": 0.88, "openai": 0.61}
OUTPUT_PER_REQ = {"teacher": (500, 1500), "student": (300, 2000)}   # 생각 토큰 포함 가정 (Opus 답 실측 평균 413)
PILOT_SEED = 20261120
DRUGS9 = ["Infliximab", "Adalimumab", "Golimumab", "Vedolizumab", "Ustekinumab",
          "Tofacitinib", "Filgotinib", "Upadacitinib", "Ozanimod"]

# ---------------------------------------------------------------- 지시문 (파일럿 뒤 고정. 해시를 meta.json에 남김)
# 일반 선생 (2026-11-23). 평가 문항·오답 분석에서 온 힌트 없이, RAG 답 검토의 일반 항목과 가이드북 목차만 쓴다.
# 2026-11-20 파일럿에 쓴 맞춤 선생(해시 601b7ce19375)은 _archive/teacher_tailored_601b7ce19375.md에 보관.
# 선생 조건의 폴더·실행 이름에 TEACHER_TAG를 붙여 맞춤 선생 결과(self_pilot·opus_pilot)와 섞이지 않게 한다.
TEACHER_TAG = "g"

TEACHER_SYSTEM = """당신은 2024 대한장연구학회 염증성장질환 보험가이드북 시험의 검토 선생입니다.
학생(다른 AI)은 검색으로 고른 가이드북 발췌만 보고 답했습니다. 당신은 학생 답과 발췌를 대조해 검토합니다.

할 일
- 학생 답이 질문에 필요한 근거를 발췌에서 찾았는지, 발췌를 정확히 옮겼는지 점검합니다.
- 부족한 점이 있으면 무엇이 부족한지와, 발췌의 어디를 다시 읽거나 가이드북의 어디를 더 찾아봐야 하는지 조언합니다.

점검할 것
1. 근거 없음: 질문에 답하는 데 필요한 내용이 발췌에 없다.
2. 잘못 옮김: 발췌에 있는 내용을 다르게 옮겼다 (일부만 옮기거나 뜻을 바꿈).
3. 질문과 다른 대상: 질문이 묻는 대상이 아닌 다른 대상에 대한 발췌를 근거로 썼다.
4. 발췌에 없는 덧붙임: 발췌에 없는 내용을 덧붙였다.
5. 빠진 내용: 질문이 묻는 것 가운데 답하지 않은 부분이 있다.
6. 형식: 지정한 답 형식을 지키지 않았다.

지켜야 할 것
- 정답을 말하지 않습니다. 판정, 수치, 답에 들어갈 항목을 쓰지 않습니다. 부족한 부분과 찾아볼 곳만 말합니다.
- 학생 답이 발췌에 근거하고 질문에 모두 답했다면 '통과'입니다. 발췌에서 가리킬 수 있는 문제가 없으면 고치게 하지 않습니다.
- 발췌 안에 근거가 있는데 잘못 읽은 문제만 있으면 판정은 '다시 읽어'. 근거가 발췌에 없으면 '더 찾아'. 둘 다 있으면 '더 찾아'.
- 찾기는 최대 3개. 약·질환·경로·쪽 종류로 가리킬 수 있으면 그렇게 쓰고 검색어는 빈 문자열로 둡니다. 쪽 종류로 가리킬 수 없으면 쪽 종류를 '검색'으로 하고 검색어를 씁니다.
- 앞에서 이미 요청한 찾기는 반복하지 않습니다.

쪽 종류 (가이드북 목차)
- 고시: 「생물학제제 및 소분자제제 급여기준 고시문」 장의 약·질환별 쪽
- 체크리스트: 같은 장의 투여 전 체크리스트 쪽
- 투약간격: 같은 장의 투약간격 쪽
- 재투여: 같은 장의 재투여 쪽
- 약 설명: 「염증성장질환의 치료」 장
- 모니터링: 「모니터링 항목 급여기준」 장
- 검색: 위로 가리킬 수 없는 내용
약은 영문 성분명, 질환은 CD(크론병)·UC(궤양성 대장염)·GIBD(장형 베체트)·없음, 경로는 IV·SC·없음으로 씁니다."""

PROBLEM_TYPES = ["근거 없음", "잘못 옮김", "질문과 다른 대상", "발췌에 없는 덧붙임", "빠진 내용", "형식"]
KINDS = ["고시", "체크리스트", "투약간격", "약 설명", "재투여", "모니터링", "검색"]
REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["판정", "문제", "찾기"],
    "properties": {
        "판정": {"type": "string", "enum": ["통과", "다시 읽어", "더 찾아"]},
        "문제": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["유형", "설명", "발췌번호"],
            "properties": {"유형": {"type": "string", "enum": PROBLEM_TYPES}, "설명": {"type": "string"},
                           "발췌번호": {"type": "array", "items": {"type": "integer"}}}}},
        "찾기": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["약", "질환", "경로", "쪽종류", "검색어"],
            "properties": {"약": {"type": "string"}, "질환": {"type": "string", "enum": ["CD", "UC", "GIBD", "없음"]},
                           "경로": {"type": "string", "enum": ["IV", "SC", "없음"]},
                           "쪽종류": {"type": "string", "enum": KINDS}, "검색어": {"type": "string"}}}},
    },
}

STUDENT_REVISE = """

검토 의견이 있을 때
사용자 메시지 끝에 이전 답과 검토 선생의 의견이 있습니다. 발췌(새로 붙은 쪽 포함)를 다시 확인해 필요하면 답을 고칩니다.
답의 근거는 발췌뿐입니다. 검토 의견이 발췌와 다르면 발췌를 따릅니다. 출력 형식은 위와 같습니다."""


# CSV 발췌 (2026-11-23): 발췌가 CSV 표의 행(약 하나·질환 하나·연령군)이라 '쪽 종류'를 '행'으로 바꾼다. 나머지는 같다.
SOURCE = "pdf"          # main()에서 --source로 정함
CSV_CORPUS = HERE.parents[2] / "data" / "RAG" / "IBD_insurance_csv_2024.jsonl"
CSV_EMBEDDINGS = HERE.parents[2] / "data" / "RAG" / "IBD_insurance_csv_2024.embeddings.jsonl"
_PDF_KINDS_BLOCK = TEACHER_SYSTEM[TEACHER_SYSTEM.index("쪽 종류 (가이드북 목차)"):TEACHER_SYSTEM.index("약은 영문 성분명")]
_PDF_FIND_RULE = "- 찾기는 최대 3개. 약·질환·경로·쪽 종류로 가리킬 수 있으면 그렇게 쓰고 검색어는 빈 문자열로 둡니다. 쪽 종류로 가리킬 수 없으면 쪽 종류를 '검색'으로 하고 검색어를 씁니다."
TEACHER_SYSTEM_CSV = TEACHER_SYSTEM.replace(_PDF_KINDS_BLOCK, """발췌 단위 (가이드북 급여 기준 표)
- 행: 약 하나·질환 하나(연령군·경로별)의 급여 기준을 모은 표의 한 행
- 검색: 약·질환으로 가리킬 수 없는 내용
""").replace(_PDF_FIND_RULE, "- 찾기는 최대 3개. 약·질환(·경로)으로 가리킬 수 있으면 쪽 종류를 '행'으로 쓰고 검색어는 빈 문자열로 둡니다. 약·질환으로 가리킬 수 없으면 쪽 종류를 '검색'으로 하고 검색어를 씁니다.")
assert TEACHER_SYSTEM_CSV.count("발췌 단위") == 1 and "쪽 종류를 '행'" in TEACHER_SYSTEM_CSV
REVIEW_SCHEMA_CSV = json.loads(json.dumps(REVIEW_SCHEMA))
REVIEW_SCHEMA_CSV["properties"]["찾기"]["items"]["properties"]["쪽종류"]["enum"] = ["행", "검색"]


def teacher_system() -> str:
    return TEACHER_SYSTEM_CSV if SOURCE == "csv" else TEACHER_SYSTEM


def review_schema() -> dict:
    return REVIEW_SCHEMA_CSV if SOURCE == "csv" else REVIEW_SCHEMA


def prompt_hash() -> str:
    text = teacher_system() + json.dumps(review_schema(), ensure_ascii=False) + STUDENT_REVISE
    return hashlib.sha256(text.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- 공용


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def write_jl(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(p)


def arm_name(arm: str) -> str:
    """폴더·실행 이름. 선생 조건은 지시문 표시(TEACHER_TAG)를 붙인다: self → self-g. route는 선생이 없어 그대로."""
    name = arm if arm in NO_TEACHER else f"{arm}-{TEACHER_TAG}"
    return name + ("-csv" if SOURCE == "csv" else "")


def resolve_dir(a) -> Path:
    """init에서 정한 폴더 (pilot이면 <이름>_pilot). 둘 다 있으면 --pilot-dir로 고른다."""
    full, pilot = ROOT / arm_name(a.arm), ROOT / f"{arm_name(a.arm)}_pilot"
    if a.pilot_dir:
        return pilot
    if full.exists():
        return full
    return pilot


def load(d: Path):
    return json.loads((d / "meta.json").read_text(encoding="utf-8")), {r["id"]: r for r in jl(d / "state.jsonl")}


def save(d: Path, meta: dict, state: dict) -> None:
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    write_jl(d / "state.jsonl", state.values())


def items_by_id() -> dict:
    out = {}
    for typ, f in TYPES.items():
        for it in jl(OUT / f):
            out[it["id"]] = it
    return out


def passages(sources: list[dict]) -> list[Passage]:
    return [Passage(id=s["id"], page=s.get("page"), section=s.get("section", ""), title=s.get("title", ""),
                    text=s["text"], drugs=tuple(s.get("drugs") or ()), disease=tuple(s.get("disease") or ()),
                    source_title="") for s in sources]


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")}


# ---------------------------------------------------------------- 가이드북 쪽 메타데이터 (정답은 쓰지 않음)

CORP = jl(CORPUS)
BY_ID = {r["id"]: r for r in CORP}
DIS_KR = {"크론": "CD", "궤양성": "UC", "베체트": "GIBD"}


def kind_of(r: dict) -> str:
    p, t, s = r["page"], r["title"], r.get("section", "")
    if "체크리스트" in t:
        return "체크리스트"
    if "재투여" in t:
        return "재투여"
    if "투약간격" in t:
        return "투약간격"
    if 35 <= p <= 57:
        return "고시"
    if "모니터링" in s:
        return "모니터링"
    if 16 <= p <= 33:
        return "약 설명"
    return "기타"


def route_of(r: dict) -> str:
    t = r["title"]
    if r["page"] in (38, 39) or " SC" in t:
        return "SC"
    if r["page"] in (35, 36, 37):
        return "IV"
    return "없음"


def as_source(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "page", "section", "title", "text", "drugs", "disease")}


def lookup(req: dict) -> list[dict]:
    """찾기 요청 하나 → 가이드북 발췌 후보 (구체적인 것 먼저). 메타데이터만 쓴다."""
    kind, drug, dis, route = req["쪽종류"], req["약"].strip().lower(), req["질환"], req["경로"]
    cands = []
    for r in CORP:
        if kind_of(r) != kind:
            continue
        drugs = [x.lower() for x in r.get("drugs") or []]
        if drug and drug != "없음" and drugs and drug not in drugs:
            continue
        if drug and drug != "없음" and not drugs and kind in ("고시", "체크리스트", "투약간격"):
            continue
        if dis != "없음" and r.get("disease") and dis not in r["disease"]:
            continue
        if route != "없음" and kind == "고시" and route_of(r) not in (route, "없음"):
            continue
        cands.append(r)
    cands.sort(key=lambda r: (len(r.get("drugs") or []) or 99, r["page"]))
    return cands


_engine = None


def search(query: str, k: int) -> list[dict]:
    """종류로 못 가리키는 요청: 기존 RAG 검색(BM25·임베딩→RRF→리랭커, PDF 코퍼스). 질문 임베딩 API 1회."""
    global _engine
    if _engine is None:
        import os
        if SOURCE == "csv":
            os.environ["RAG_EMBEDDINGS"] = str(CSV_EMBEDDINGS)
        else:
            os.environ.pop("RAG_EMBEDDINGS", None)   # 기본 = 가이드북 PDF 임베딩
        import csv_rag_retrieve  # noqa: F401  (질문 임베딩에 30초 제한을 거는 패치)
        from app.rag.pipeline import Engine
        _engine = Engine.load()
    hits = _engine.trace(query)["rerank"]
    pool = CSV_BY_ID if SOURCE == "csv" else BY_ID
    return [as_source(pool[h.passage.id]) for h in hits[:k] if h.passage.id in pool]


CSV_CORP = jl(CSV_CORPUS)
CSV_BY_ID = {r["id"]: r for r in CSV_CORP}
DIS_CODE = {"CD": "크론병", "UC": "궤양성 대장염", "GIBD": "장형 베체트"}


def lookup_csv(req: dict) -> list[dict]:
    """찾기 요청 → CSV 행 (약 이름·질환·경로 메타데이터만). 성인 행 먼저, 소아·누공 행은 뒤로."""
    drug, dis, route = req["약"].strip().lower(), DIS_CODE.get(req["질환"]), req["경로"]
    if not drug or drug == "없음":
        return []
    cands = [r for r in CSV_CORP if (r.get("drugs") or [""])[0].lower() == drug
             and (dis is None or dis in (r.get("disease") or []))
             and (route == "없음" or f"-{route}-" in r["id"] or ("-IV-" not in r["id"] and "-SC-" not in r["id"]))]
    cands.sort(key=lambda r: (("PED" in r["id"].upper()) + ("fistula" in r["id"]), r["id"]))
    return cands


def rule_b(item: dict, sources: list[dict]) -> list[dict]:
    """② 라우팅만: simulate_retrieval.py의 규칙 B와 같은 뜻 (질문 대괄호의 약·질환, D형은 환자 질환의 9개 성분 고시 쪽 →
    붙은 고시 쪽마다 같은 약·질환의 체크리스트·투약간격 쪽)."""
    have = {s["id"] for s in sources}
    add = []

    def push(r):
        if r["id"] not in have:
            have.add(r["id"])
            add.append(as_source(r))

    if item["type"] == "D":
        dis = item["patient"]["dis"]
        for r in CORP:
            if kind_of(r) == "고시" and dis in (r.get("disease") or []) and set(r.get("drugs") or []) & set(DRUGS9):
                push(r)
    else:
        m = re.match(r"\[([^\]]+)\]", item["question"])
        head = m.group(1) if m else ""
        dis = {c for k, c in DIS_KR.items() if k in head}
        names = {d for r in CORP for d in (r.get("drugs") or []) if d.lower() in head.lower()}
        if names and dis:
            cand = [r for r in CORP if set(r.get("drugs") or []) & names and set(r.get("disease") or []) & dis
                    and len(r.get("drugs") or []) <= 4]
            crit = [r for r in cand if kind_of(r) == "고시"]
            for r in crit or cand:
                push(r)
    for s in list(sources) + list(add):
        r = BY_ID.get(s["id"])
        if not r or kind_of(r) != "고시":
            continue
        for q in CORP:
            if kind_of(q) in ("체크리스트", "투약간격") and set(q.get("drugs") or []) & set(r.get("drugs") or []) \
                    and set(q.get("disease") or []) & set(r.get("disease") or []):
                push(q)
    return add


# ---------------------------------------------------------------- init


def init(a) -> int:
    pilot = bool(a.pilot or a.pick_wrong or a.pick_right)
    d = ROOT / (f"{arm_name(a.arm)}_pilot" if pilot else arm_name(a.arm))
    if (d / "state.jsonl").exists():
        print(f"이미 있음: {d} (다시 하려면 폴더를 옮기세요)", file=sys.stderr)
        return 1
    old_q = {r["id"]: r["question"] for r in jl(A_BACKUP)}
    state, skipped, orig = {}, [], {}
    rng = random.Random(PILOT_SEED)
    base_run = "csvrag" if SOURCE == "csv" else "agent"   # 0회차 답: CSV-RAG 답 또는 PDF 에이전트 답
    for typ, f in TYPES.items():
        if a.types and typ not in a.types:
            continue
        items = jl(OUT / f)
        if a.pick_wrong or a.pick_right:
            # 파일럿 표본만 고르는 데 기존 에이전트 채점을 쓴다 (루프에는 정답·채점을 주지 않음)
            g = {r["id"]: r["최종"] for r in jl(EV / f"{RUN_PREFIX[typ]}{base_run}_{student_label()}" / GRADED[typ])}
            wrong = [it for it in items if g.get(it["id"]) in ("틀림", "부분")]
            right = [it for it in items if g.get(it["id"]) == "맞음"]
            items = sorted(rng.sample(wrong, min(a.pick_wrong, len(wrong))) + rng.sample(right, min(a.pick_right, len(right))),
                           key=lambda x: x["id"])
            for it in items:
                orig[it["id"]] = g[it["id"]]
        elif a.pilot:
            items = sorted(rng.sample(items, a.pilot), key=lambda x: x["id"])
        agent = {r["id"]: r for r in jl(EV / f"{RUN_PREFIX[typ]}{base_run}_{student_label()}" / "answers.jsonl")}
        for it in items:
            row = agent.get(it["id"])
            asked = (row or {}).get("질문") or (old_q.get(it["id"]) if typ == "A" else None)
            sources = ((row or {}).get("응답") or {}).get("sources") or []
            if not row or asked != it["question"] or not sources:
                skipped.append(it["id"])
                continue
            st = {"id": it["id"], "type": typ, "question": it["question"], "round": 0,
                  "answers": [row["reply"].strip()], "sources0": len(sources), "sources": sources,
                  "reviews": [], "added": [], "status": "review", "원래 채점": orig.get(it["id"])}
            if a.arm == "route":
                if SOURCE == "csv":
                    sys.exit("route(규칙 B)는 PDF 쪽 규칙이라 --source csv에서는 쓰지 않습니다.")
                add = rule_b(it, sources)
                st["added"].append({"round": 1, "요청": "규칙 B", "붙인 발췌": [s["id"] for s in add], "방법": "규칙"})
                st["sources"] = sources + add
                st["status"] = "student"
            elif a.arm == "reask":     # 같은 발췌·같은 지시문으로 한 번 더 답 (gpt 답의 우연한 변화를 재는 대조군)
                st["status"] = "student"
            state[it["id"]] = st
    d.mkdir(parents=True, exist_ok=True)
    meta = {"arm": a.arm, "pilot": pilot, "표본": {"pilot": a.pilot, "오답": a.pick_wrong, "정답": a.pick_right},
            "seed": PILOT_SEED if pilot else None, "teacher": None if a.arm in NO_TEACHER else teacher_of(a.arm),
            "teacher_prompt": None if a.arm in NO_TEACHER else f"일반({TEACHER_TAG})",
            "source": SOURCE, "types": a.types or list(TYPES), "round0": base_run,
            "student": student_label(), "max_rounds": MAX_ROUNDS, "per_request": PER_REQUEST, "per_round": PER_ROUND,
            "prompt_hash": prompt_hash(), "created": datetime.now().isoformat(timespec="seconds"),
            "skipped(질문 다름·답 없음)": skipped, "batches": [], "pending": None}
    save(d, meta, state)
    by = {}
    for s in state.values():
        by[s["type"]] = by.get(s["type"], 0) + 1
    print(f"[{d.name}] 문항 {len(state)} {by} · 건너뜀 {len(skipped)} · 지시문 해시 {meta['prompt_hash']}")
    print("다음: next")
    return 0


# ---------------------------------------------------------------- 요청 만들기


def teacher_user(st: dict) -> str:
    prev = [f"- {q['쪽종류']} / {q['약']} / {q['질환']} / {q['경로']} / {q['검색어']}".rstrip(" /")
            for rv in st["reviews"] for q in (rv.get("출력") or {}).get("찾기", [])]
    return (f"문항 형식: {FORMAT_NAME[st['type']]}\n\n질문:\n{st['question']}\n\n"
            f"가이드북 발췌:\n{_context(passages(st['sources']))}\n\n학생 답:\n{st['answers'][-1]}\n\n"
            f"앞에서 이미 요청한 찾기:\n" + ("\n".join(prev) if prev else "없음"))


def student_messages(st: dict) -> tuple[str, str]:
    style = E.ANSWER_STYLE.get(st["type"])
    system = _ANSWER_STYLE[style] if style else _ANSWER_ONLY
    user = f"질문:\n{st['question']}\n\n가이드북 발췌:\n{_context(passages(st['sources']))}"
    if not st["reviews"]:          # route: 쪽만 붙이고 처음처럼 답함 (에이전트와 같은 문장)
        return system, user
    rv = st["reviews"][-1]["출력"]
    notes = "\n".join(f"- [{p['유형']}] {p['설명']}" + (f" (발췌 {', '.join(map(str, p['발췌번호']))})" if p["발췌번호"] else "")
                      for p in rv.get("문제", [])) or "- (구체적 지적 없음)"
    added = st["added"][-1] if st["added"] and st["added"][-1]["round"] == st["round"] + 1 else None
    if added is not None:
        notes += ("\n- 새로 붙인 발췌: " + ", ".join(added["붙인 발췌"])) if added["붙인 발췌"] else "\n- 요청한 쪽을 가이드북에서 더 찾지 못함"
    user += f"\n\n이전 답:\n{st['answers'][-1]}\n\n검토 선생 의견 (판정: {rv['판정']}):\n{notes}"
    return system + STUDENT_REVISE, user


LOCAL_JSON_NOTE = """

출력 형식
아래 JSON 스키마를 따르는 JSON 객체 하나만 출력합니다. 다른 문장은 쓰지 않습니다.
"""


def local_request(cid: str, kind: str, system: str, user: str) -> dict:
    """로컬 모델용 요청 (run_local_batch.py가 읽음). 선생은 API의 json_schema 기능 대신 스키마를 지시문 끝에 붙인다."""
    if kind == "teacher":
        system = system + LOCAL_JSON_NOTE + json.dumps(review_schema(), ensure_ascii=False)
    return {"custom_id": cid, "kind": kind, "model": STUDENTS[STUDENT][1],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}


def teacher_request(provider: str, model: str, cid: str, st: dict) -> dict:
    user = teacher_user(st)
    if provider == "local":
        return local_request(cid, "teacher", teacher_system(), user)
    if provider == "openai":
        return {"custom_id": cid, "method": "POST", "url": "/v1/responses",
                "body": {"model": model, "input": [{"role": "system", "content": teacher_system()},
                                                   {"role": "user", "content": user}],
                         "text": {"format": {"type": "json_schema", "name": "review", "schema": review_schema(), "strict": True}}}}
    return {"custom_id": cid, "params": {
        "model": model, "max_tokens": OPUS_MAX_TOKENS,
        "output_config": {"effort": OPUS_EFFORT, "format": {"type": "json_schema", "schema": review_schema()}},
        "system": teacher_system(), "messages": [{"role": "user", "content": user}]}}


def student_request(cid: str, st: dict) -> dict:
    system, user = student_messages(st)
    if STUDENTS[STUDENT][0] == "local":
        return local_request(cid, "student", system, user)
    return {"custom_id": cid, "method": "POST", "url": "/v1/responses",
            "body": {"model": STUDENT_MODEL, "input": [{"role": "system", "content": system},
                                                       {"role": "user", "content": user}]}}


# ---------------------------------------------------------------- 쪽 찾기 (코드)


def expand(st: dict) -> None:
    rv = st["reviews"][-1]["출력"]
    have = {s["id"] for s in st["sources"]}
    added, log = [], []
    for q in rv.get("찾기", [])[:3]:
        if len(added) >= PER_ROUND:
            break
        how = "조회"
        cands = (lookup_csv(q) if SOURCE == "csv" else lookup(q)) if q["쪽종류"] != "검색" else []
        if not cands and (q["검색어"].strip() or q["쪽종류"] == "검색"):
            how = "검색"
            query = q["검색어"].strip() or " ".join(x for x in (q["약"], q["질환"], q["쪽종류"]) if x and x != "없음")
            cands = search(query, 6)
        got = []
        for c in cands:
            if c["id"] in have or len(got) >= PER_REQUEST or len(added) + len(got) >= PER_ROUND:
                continue
            have.add(c["id"])
            got.append(as_source((CSV_BY_ID if SOURCE == "csv" else BY_ID).get(c["id"], c)))
        added += got
        log.append({"요청": q, "방법": how, "붙인 발췌": [g["id"] for g in got],
                    "이유": None if got else ("후보 없음" if not cands else "이미 발췌에 있음/상한")})
    st["sources"] = st["sources"] + added
    st["added"].append({"round": st["round"] + 1, "요청": log, "붙인 발췌": [g["id"] for g in added], "방법": "선생 요청"})
    st["status"] = "student"


# ---------------------------------------------------------------- 누설 검사 (선생 출력마다, 정답은 쓰지 않음)

VERDICT_WORDS = re.compile(r"(판정|답)[은는이가]?\s*['\"“]?\s*(예|아니오|판단 불가)\b|정답은|급여(가)? (인정된다|된다|안 된다|불가하다)")
NAME_PUSH = re.compile(r"(인정해야|넣어야|포함해야|추가해야)")


def leak_flags(st: dict, out: dict) -> list[str]:
    allowed = numbers(st["question"]) | numbers(st["answers"][-1]) | numbers(" ".join(s["text"] for s in st["sources"]))
    flags = []
    for p in out.get("문제", []):
        # 발췌 번호 표기([7], 발췌 [3]·[4], 발췌 5)는 숫자 검사에서 뺀다 (2026-11-20 파일럿: 거짓 경보 2건)
        text = re.sub(r"\[\d+\]|발췌\s*\d+", " ", p["설명"])
        extra = numbers(text) - allowed
        if extra:
            flags.append(f"발췌 밖 숫자 {sorted(extra)[:5]}")
        if VERDICT_WORDS.search(p["설명"]):
            flags.append("판정 표현")
        if st["type"] == "D" and NAME_PUSH.search(p["설명"]) and any(x.lower() in p["설명"].lower() for x in DRUGS9):
            flags.append("D형 약 지목")
    return flags


# ---------------------------------------------------------------- next / submit / status / fetch


def nxt(a) -> int:
    d = resolve_dir(a)
    meta, state = load(d)
    if meta["pending"]:
        print(f"아직 받지 않은 배치가 있습니다: {meta['pending']['name']} (submit/fetch 먼저)")
        return 1
    todo_expand = [s for s in state.values() if s["status"] == "expand"]
    if todo_expand:
        print(f"쪽 찾기 {len(todo_expand)}문항 (코드)…", flush=True)
        for s in todo_expand:
            expand(s)
        save(d, meta, state)
    review = [s for s in state.values() if s["status"] == "review"]
    student = [s for s in state.values() if s["status"] == "student"]
    if review and a.arm not in NO_TEACHER:
        provider, model = teacher_of(a.arm)
        kind, rows = "teacher", review
        rnd = max(s["round"] for s in review) + 1
        reqs = [teacher_request(provider, model, f"t{i:05d}", s) for i, s in enumerate(rows)]
    elif student:
        provider, model, kind, rows = STUDENTS[STUDENT][0], STUDENTS[STUDENT][1], "student", student
        rnd = max(s["round"] for s in student) + 1
        reqs = [student_request(f"s{i:05d}", s) for i, s in enumerate(rows)]
    else:
        counts = {}
        for s in state.values():
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        print(f"할 일 없음 {counts}. 다음: finalize")
        return 0
    name = f"{len(meta['batches']) + 1:02d}_{kind}_r{rnd}"
    bd = d / "batches" / name
    bd.mkdir(parents=True, exist_ok=True)
    write_jl(bd / "requests.jsonl", reqs)
    mapping = {r["custom_id"]: s["id"] for r, s in zip(reqs, rows)}
    (bd / "map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    chars = sum(len(json.dumps(r, ensure_ascii=False)) for r in reqs)
    meta["pending"] = {"name": name, "kind": kind, "provider": provider, "model": model, "requests": len(reqs),
                       "built": datetime.now().isoformat(timespec="seconds")}
    save(d, meta, state)
    if provider == "local":
        print(f"[{d.name}] {name}: {kind} 요청 {len(reqs)}개 · 로컬 {model} (요금 없음) · 입력 약 {chars:,}자")
        print(f"다음: submit --arm {a.arm} --student {STUDENT} --yes → run_local_batch.py --dir {bd}")
        return 0
    tin = chars * TOKENS_PER_CHAR[provider]
    print(f"[{d.name}] {name}: {kind} 요청 {len(reqs)}개 · {model} · 입력 약 {chars:,}자 → 약 {tin / 1e3:,.0f}K 토큰 "
          f"(실측 비율 {TOKENS_PER_CHAR[provider]}토큰/자)")
    if model in PRICE:
        pin, pout = PRICE[model]
        lo, hi = ((tin * pin + len(reqs) * o * pout) / 1e6 * 0.5 for o in OUTPUT_PER_REQ[kind])
        print(f"  예상 비용(배치 50%, 출력 {OUTPUT_PER_REQ[kind][0]}~{OUTPUT_PER_REQ[kind][1]}토큰/요청 가정): ${lo:.2f} ~ ${hi:.2f}")
    else:
        print(f"  {model} 단가가 기록에 없어 금액은 계산하지 않음 (fetch 뒤 실제 토큰을 보고)")
    print(f"API 안 씀. 제출: submit --arm {a.arm} --yes")
    return 0


def openai_client():
    from openai import OpenAI
    key = E.load_env().get("OPENAI_API_KEY", "")
    if not key:
        sys.exit("OPENAI_API_KEY 없음")
    return OpenAI(api_key=key, timeout=120, max_retries=3)


def anthropic_client():
    import anthropic
    key = E.load_env().get("ANTHROPIC_API_KEY", "")
    if not key:
        sys.exit("ANTHROPIC_API_KEY 없음")
    return anthropic.Anthropic(api_key=key, timeout=120, max_retries=3)


def submit(a) -> int:
    d = resolve_dir(a)
    meta, state = load(d)
    p = meta["pending"]
    if not p:
        print("제출할 배치가 없습니다 (next 먼저).")
        return 1
    if p.get("batch_id"):
        print(f"이미 제출함: {p['batch_id']}")
        return 1
    bd = d / "batches" / p["name"]
    if not a.yes:
        print(f"{p['name']}: 요청 {p['requests']}개 ({p['model']})를 제출하면 과금됩니다. --yes를 붙이세요.")
        return 1
    if p["provider"] == "local":
        p.update(batch_id="local")
        p["submitted"] = datetime.now().isoformat(timespec="seconds")
        save(d, meta, state)
        print(f"로컬 실행 표시함: {p['name']}. 답 채우기: run_local_batch.py --dir {bd}")
        return 0
    if p["provider"] == "openai":
        c = openai_client()
        f = c.files.create(file=(bd / "requests.jsonl").open("rb"), purpose="batch")
        b = c.batches.create(input_file_id=f.id, endpoint="/v1/responses", completion_window="24h")
        p.update(batch_id=b.id, input_file_id=f.id)
        status = b.status
    else:
        b = anthropic_client().messages.batches.create(requests=jl(bd / "requests.jsonl"))
        p.update(batch_id=b.id)
        status = b.processing_status
    p["submitted"] = datetime.now().isoformat(timespec="seconds")
    save(d, meta, state)
    print(f"제출함: {p['name']} {p['batch_id']} 상태 {status}")
    return 0


def status(a) -> int:
    d = resolve_dir(a)
    meta, _ = load(d)
    p = meta["pending"]
    if not p or not p.get("batch_id"):
        print("진행 중인 배치 없음")
        return 0
    if p["provider"] == "local":
        bd = d / "batches" / p["name"]
        print(f"{p['name']} 로컬 {len(jl(bd / 'results_local.jsonl'))}/{p['requests']}")
        return 0
    if p["provider"] == "openai":
        b = openai_client().batches.retrieve(p["batch_id"])
        print(f"{p['name']} {b.id} {b.status} {b.request_counts}")
    else:
        b = anthropic_client().messages.batches.retrieve(p["batch_id"])
        print(f"{p['name']} {b.id} {b.processing_status} {b.request_counts}")
    return 0


def output_text(body: dict) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    return "".join(part.get("text", "") for item in body.get("output", []) if item.get("type") == "message"
                   for part in item.get("content", []) if part.get("type") in ("output_text", "text"))


def local_json(text: str) -> str:
    """로컬 선생 출력에서 JSON 객체를 꺼낸다 (생각 부분은 run_local_batch.py가 이미 뗌). 못 꺼내면 빈 문자열."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return ""
    try:
        return json.dumps(json.loads(text[a:b + 1]), ensure_ascii=False)
    except json.JSONDecodeError:
        return ""


def collect(p: dict, bd: Path) -> tuple[dict, list, dict]:
    """배치 결과 → {custom_id: text}, 실패 목록, usage. 끝나지 않았으면 None."""
    texts, failed, usage = {}, [], {"input_tokens": 0, "output_tokens": 0}
    if p["provider"] == "local":
        rows = {r["custom_id"]: r for r in jl(bd / "results_local.jsonl")}
        if len(rows) < p["requests"]:
            print(f"아직 끝나지 않음: 로컬 {len(rows)}/{p['requests']} (run_local_batch.py --dir {bd})")
            return None, None, None
        for cid, r in rows.items():
            usage["input_tokens"] += r.get("input_tokens", 0)
            usage["output_tokens"] += r.get("output_tokens", 0)
            text = (r.get("text") or "").strip()
            if p["kind"] == "teacher":
                text = local_json(text)
            if text:
                texts[cid] = text
            else:
                failed.append({"custom_id": cid, "오류": "빈 답 또는 JSON 아님" + ("" if r.get("finished", True) else " (길이 한도)")})
        return texts, failed, usage
    if p["provider"] == "openai":
        c = openai_client()
        b = c.batches.retrieve(p["batch_id"])
        if b.status != "completed":
            print(f"아직 끝나지 않음: {b.status} {b.request_counts}")
            return None, None, None
        raw = c.files.content(b.output_file_id).text if b.output_file_id else ""
        (bd / "results_raw.jsonl").write_text(raw, encoding="utf-8")
        if b.error_file_id:
            (bd / "errors_raw.jsonl").write_text(c.files.content(b.error_file_id).text, encoding="utf-8")
        for line in raw.splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            resp = r.get("response") or {}
            body = resp.get("body") or {}
            u = body.get("usage") or {}
            usage["input_tokens"] += u.get("input_tokens", 0)
            usage["output_tokens"] += u.get("output_tokens", 0)
            text = output_text(body).strip() if resp.get("status_code") == 200 else ""
            if text:
                texts[r["custom_id"]] = text
            else:
                failed.append({"custom_id": r["custom_id"], "오류": f"HTTP {resp.get('status_code')} {str(r.get('error'))[:200]}"})
    else:
        c = anthropic_client()
        b = c.messages.batches.retrieve(p["batch_id"])
        if b.processing_status != "ended":
            print(f"아직 끝나지 않음: {b.processing_status} {b.request_counts}")
            return None, None, None
        raw = []
        for r in c.messages.batches.results(p["batch_id"]):
            raw.append(r.to_dict())
            if r.result.type != "succeeded":
                failed.append({"custom_id": r.custom_id, "오류": r.result.type})
                continue
            msg = r.result.message
            usage["input_tokens"] += msg.usage.input_tokens
            usage["output_tokens"] += msg.usage.output_tokens
            text = "".join(blk.text for blk in msg.content if blk.type == "text").strip()
            if msg.stop_reason != "end_turn" or not text:
                failed.append({"custom_id": r.custom_id, "오류": f"stop_reason={msg.stop_reason}, 글자 {len(text)}"})
                continue
            texts[r.custom_id] = text
        write_jl(bd / "results_raw.jsonl", raw)
    pin, pout = PRICE.get(p["model"], (None, None))
    if pin:
        usage["cost_usd"] = round((usage["input_tokens"] * pin + usage["output_tokens"] * pout) / 1e6 * 0.5, 4)
    return texts, failed, usage


def fetch(a) -> int:
    d = resolve_dir(a)
    meta, state = load(d)
    p = meta["pending"]
    if not p or not p.get("batch_id"):
        print("받을 배치가 없습니다.")
        return 1
    bd = d / "batches" / p["name"]
    texts, failed, usage = collect(p, bd)
    if texts is None:
        return 1
    mapping = json.loads((bd / "map.json").read_text(encoding="utf-8"))
    counts = {}
    for cid, iid in mapping.items():
        st = state[iid]
        if p["kind"] == "teacher":
            text = texts.get(cid)
            try:
                out = json.loads(text) if text else None
                if not isinstance(out, dict) or out.get("판정") not in ("통과", "다시 읽어", "더 찾아"):
                    raise ValueError
            except (ValueError, json.JSONDecodeError):
                st["reviews"].append({"round": st["round"] + 1, "출력": None, "오류": (text or "응답 없음")[:300], "batch": p["batch_id"]})
                st["status"] = "done"          # 선생 출력이 깨지면 지금 답으로 확정 (보고서에 셈)
                counts["선생 오류"] = counts.get("선생 오류", 0) + 1
                continue
            st["reviews"].append({"round": st["round"] + 1, "출력": out, "누설 의심": leak_flags(st, out),
                                  "선생": p["model"], "batch": p["batch_id"]})
            v = out["판정"]
            counts[v] = counts.get(v, 0) + 1
            if v == "통과":
                st["status"] = "passed"
            elif v == "더 찾아" and out.get("찾기"):
                st["status"] = "expand"
            else:
                st["status"] = "student"       # 다시 읽어 (또는 찾기 없는 더 찾아)
        else:
            text = texts.get(cid)
            if not text:
                st.setdefault("오류", []).append({"round": st["round"] + 1, "batch": p["batch_id"]})
                st["status"] = "done"          # 학생 재답 실패: 이전 답 유지
                counts["학생 오류"] = counts.get("학생 오류", 0) + 1
                continue
            st["answers"].append(text)
            st["round"] += 1
            st["status"] = "done" if (a.arm in NO_TEACHER or st["round"] >= MAX_ROUNDS) else "review"
            counts["재답"] = counts.get("재답", 0) + 1
    (bd / "failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
    (bd / "usage.json").write_text(json.dumps(usage, indent=1), encoding="utf-8")
    meta["batches"].append({**p, "fetched": datetime.now().isoformat(timespec="seconds"), "usage": usage,
                            "failed": len(failed), "결과": counts})
    meta["pending"] = None
    save(d, meta, state)
    print(f"{p['name']}: {counts} · 실패 {len(failed)} · 토큰 입력 {usage['input_tokens']:,} 출력 {usage['output_tokens']:,}"
          + (f" · ${usage['cost_usd']:.2f}" if "cost_usd" in usage else ""))
    print("다음: next")
    return 0


# ---------------------------------------------------------------- finalize / report (무료)


def finalize(a) -> int:
    d = resolve_dir(a)
    meta, state = load(d)
    suffix = "_pilot" if meta["pilot"] else ""
    runs = {}
    for st in state.values():
        last = st["reviews"][-1]["출력"] if st["reviews"] and st["reviews"][-1].get("출력") else None
        runs.setdefault(st["type"], []).append({
            "id": st["id"], "질문": st["question"], "reply": st["answers"][-1],
            "대상": f"{student_label()} + 검토 루프({arm_name(a.arm)})", "시각": datetime.now().isoformat(timespec="seconds"),
            "응답": {"answer": st["answers"][-1], "sources": st["sources"], "회차": st["round"], "상태": st["status"],
                     "마지막 선생 판정": last["판정"] if last else None, "답 이력": st["answers"]}})
    for typ, rows in runs.items():
        run = f"{RUN_PREFIX[typ]}loop-{arm_name(a.arm)}{suffix}_{student_label()}"
        write_jl(EV / run / "answers.jsonl", rows)
        tool = "score_cases.py" if typ in ("C", "D") else "regrade_v2_batch.py build --job"
        print(f"{run}: {len(rows)}개 → 채점: {tool} …")
    unfinished = [s["id"] for s in state.values() if s["status"] not in ("done", "passed")]
    if unfinished:
        print(f"주의: 루프가 끝나지 않은 문항 {len(unfinished)}개는 마지막 답으로 넣었습니다.")
    return 0


def report(a) -> int:
    d = resolve_dir(a)
    meta, state = load(d)
    rows = list(state.values())
    verdicts, leaks, flagged, added, changed, rounds = {}, 0, [], 0, 0, {}
    for st in rows:
        for rv in st["reviews"]:
            v = (rv.get("출력") or {}).get("판정", "오류")
            verdicts[f"r{rv['round']} {v}"] = verdicts.get(f"r{rv['round']} {v}", 0) + 1
            if rv.get("누설 의심"):
                leaks += 1
                flagged.append((st["id"], rv["누설 의심"]))
        added += sum(len(x["붙인 발췌"]) for x in st["added"])
        changed += st["answers"][-1].strip() != st["answers"][0].strip()
        rounds[st["round"]] = rounds.get(st["round"], 0) + 1
    reviews = sum(len(st["reviews"]) for st in rows)
    cost = sum((b.get("usage") or {}).get("cost_usd", 0) for b in meta["batches"])
    tokens = {k: sum((b.get("usage") or {}).get(k, 0) for b in meta["batches"]) for k in ("input_tokens", "output_tokens")}
    out = {"폴더": d.name, "문항": len(rows), "지시문 해시": meta["prompt_hash"], "선생 판정(회차별)": dict(sorted(verdicts.items())),
           "누설 의심 검토": f"{leaks}/{reviews}", "붙인 발췌 수(합)": added, "최종 답이 0회차와 다름": changed,
           "학생 재답 회차 분포": rounds, "배치": len(meta["batches"]), "토큰": tokens,
           "기록된 비용(Opus만, 배치)": round(cost, 2), "누설 의심 목록": flagged[:30]}
    (d / "report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="선생–학생 검토·재검색 루프 (배치)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init", "next", "submit", "status", "fetch", "finalize", "report"):
        x = sub.add_parser(name)
        x.add_argument("--arm", required=True, choices=ARMS)
        x.add_argument("--student", default="gpt", choices=list(STUDENTS), help="학생 모델: gpt(gpt-5.6-terra, 배치) / qwen(로컬 Qwen3-14B)")
        x.add_argument("--source", default="pdf", choices=["pdf", "csv"], help="발췌 출처: pdf(가이드북 쪽) / csv(CSV 행, 0회차 = CSV-RAG 답)")
        x.add_argument("--pilot-dir", action="store_true", help="전체 폴더가 있어도 <arm>_pilot을 고름")
        if name == "init":
            x.add_argument("--pilot", type=int, default=0, help="유형마다 N문항 (시드 고정)")
            x.add_argument("--pick-wrong", type=int, default=0, help="파일럿: 유형마다 기존 에이전트 오답(틀림·부분) N문항")
            x.add_argument("--types", nargs="+", choices=list(TYPES), help="이 유형만")
            x.add_argument("--pick-right", type=int, default=0, help="파일럿: 유형마다 기존 에이전트 정답 N문항")
        if name == "submit":
            x.add_argument("--yes", action="store_true")
    a = p.parse_args()
    global SOURCE, STUDENT, ROOT
    SOURCE, STUDENT = a.source, a.student
    if STUDENT != "gpt":
        ROOT = EV / f"teacher_loop_{student_label()}"
    return {"init": init, "next": nxt, "submit": submit, "status": status, "fetch": fetch,
            "finalize": finalize, "report": report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
