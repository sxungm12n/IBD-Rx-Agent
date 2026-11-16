#!/usr/bin/env python3
"""인용문 원문 대조 (API 없음, 저장된 답만 사용, 2026-11-15).

A·A2형 답(기본 AI, 에이전트)을 가이드북 원문과 글자 단위로 비교한다. 사람 판단 없이 다시 계산되는 지표를 만든다.

글자 맞추기
  - 비교 전에 NFKC 정규화 후 한글·영문 소문자·숫자만 남긴다(띄어쓰기·문장부호·괄호 차이는 무시).
  - '같은 글자 N개 이상 연속'(N = 8)이 원문에 있으면 그 글자들을 '원문에 있음'으로 본다.

지표 (답마다)
  원문 일치도   답 글자 중 가이드북 원문(70조각 전체)에 연속 8자 이상으로 있는 글자 비율
  발췌 일치도   에이전트만: 답 글자 중 그 문항에서 검색해 온 5쪽에 있는 글자 비율
  원문에 없는 구절  답에서 원문과 연속 8자 이상 겹치지 않는 10자 이상 구간 (원문에 없는 덧붙임 후보)
  조건 누락     답이 옮겨 온 가이드북 문장(답과 8자 조각이 가장 많이 겹치는 문장)에서, 답이 덮은 구간과 그 직후 30자 안에
                반응 조항의 조건 단어(내약성·금기·부작용·중단)가 있는데 답에는 그 단어가 없으면 누락으로 센다.
                조건 단어는 A형 채점 열쇠의 '반응 조항'(반응 없음 / ·불내성·금기 / ·부작용 중단) 정의에서 가져왔다.
                (처음에 정답 문장과 직접 비교했으나, 정답은 코드가 줄여 쓴 문장이라 맞는 답도 '빠짐'으로 잡혀 버렸다.)
  답 분류       '적혀 있지 않다' / 원문 그대로(일치도 ≥ 0.8) / 일부 바꿔 씀(0.5~0.8) / 자기 말(< 0.5)

결과: eval_out/quote_check.json, 콘솔 요약
"""
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

S1 = Path(__file__).resolve().parent
sys.path.insert(0, str(S1))
import eval_a as E  # noqa: E402  (answer_body, NOT_WRITTEN: 채점과 같은 답 본문 규칙)

CORPUS = S1.parents[2] / "data" / "RAG" / "IBD_insurance_guide_2024.jsonl"
OUT, EV = S1 / "output", S1 / "eval_out"
N_MATCH, TAIL = 8, 30
COND_WORDS = ["내약성", "금기", "부작용", "중단"]
RUNS = {"A": ("llm_gpt-5.6-terra", "agent_gpt-5.6-terra", "a_items.jsonl"),
        "A2": ("a2_llm_gpt-5.6-terra", "a2_agent_gpt-5.6-terra", "a2_items.jsonl")}


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def norm(s: str) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", unicodedata.normalize("NFKC", s or "").lower())


def grams(s: str, n: int) -> set:
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def covered(s: str, gram_set: set, n: int) -> list:
    """s의 글자마다, 그 글자를 덮는 n-글자 조각이 gram_set에 있으면 True."""
    mask = [False] * len(s)
    for i in range(len(s) - n + 1):
        if s[i:i + n] in gram_set:
            for j in range(i, i + n):
                mask[j] = True
    return mask


def runs(s: str, mask: list, keep: bool) -> list:
    """mask 값이 keep인 연속 구간의 글자열."""
    out, cur = [], ""
    for ch, m in zip(s, mask):
        if m == keep:
            cur += ch
        elif cur:
            out.append(cur); cur = ""
    if cur:
        out.append(cur)
    return out


# ---- 가이드북 원문 (조각 머리의 '[2024 … · p.N · 제목]' 줄은 뺀다) ----
PAGE_TEXT = defaultdict(str)
for r in jl(CORPUS):
    body = r["text"].split("\n", 1)[1] if r["text"].startswith("[") else r["text"]
    PAGE_TEXT[int(r["page"])] += " " + body
ALL_GRAMS = set().union(*(grams(norm(t), N_MATCH) for t in PAGE_TEXT.values()))
PAGE_GRAMS = {p: grams(norm(t), N_MATCH) for p, t in PAGE_TEXT.items()}
SENTS = [(p, n) for p, t in PAGE_TEXT.items()
         for s in re.split(r"\n+|(?<=[다음함])\.\s|(?<=\.)\s(?=[가-힣A-Z])", t) if len(n := norm(s)) >= 15]


def source_sentence(a: str):
    """답과 8자 조각이 가장 많이 겹치는 가이드북 문장 (쪽, 정규화 문장, 답이 덮은 글자 표시)."""
    ga, best = grams(a, N_MATCH), None
    for p, n in SENTS:
        k = len(ga & grams(n, N_MATCH))
        if k and (best is None or k > best[0]):
            best = (k, p, n)
    if not best:
        return None
    _, p, n = best
    return p, n, covered(n, ga, N_MATCH)


def check(item, rec, agent: bool) -> dict:
    reply = rec.get("reply") or ""
    body = E.answer_body(reply)
    a = norm(body)
    row = {"id": item["id"], "유형": item["type"], "gate": item["gate"], "기준": item["기준"],
           "본문항": not str(item["기준"]).startswith("금기"), "답": body}
    if E.NOT_WRITTEN.search(body):
        row["답 분류"] = "적혀 있지 않다"
    if not a:
        row["답 분류"] = "빈 답"
        return row
    m_all = covered(a, ALL_GRAMS, N_MATCH)
    row["원문 일치도"] = round(sum(m_all) / len(a), 3)
    row["원문에 없는 구절"] = [x for x in runs(a, m_all, False) if len(x) >= 10]
    if agent:
        pages = sorted({int(s["page"]) for s in (rec.get("응답") or {}).get("sources", []) if str(s.get("page", "")).isdigit()})
        g = set().union(*(PAGE_GRAMS.get(p, set()) for p in pages)) if pages else set()
        row["검색된 쪽"] = pages
        row["발췌 일치도"] = round(sum(covered(a, g, N_MATCH)) / len(a), 3)
    if "답 분류" not in row:
        p = row["원문 일치도"]
        row["답 분류"] = "원문 그대로" if p >= 0.8 else ("일부 바꿔 씀" if p >= 0.5 else "자기 말")
    src = source_sentence(a)
    if src:
        p, n, m = src
        idx = [i for i, x in enumerate(m) if x]
        region = n[idx[0]:idx[-1] + 1 + TAIL]
        row["옮겨 온 원문 쪽"] = p
        row["조건 누락"] = [w for w in COND_WORDS if w in region and w not in a]
    return row


def main():
    rows = []
    for typ, (base_run, agent_run, items_file) in RUNS.items():
        items = {i["id"]: i for i in jl(OUT / items_file)}
        for side, run in (("기본 AI", base_run), ("에이전트", agent_run)):
            answers = {r["id"]: r for r in jl(EV / run / "answers.jsonl")}
            graded = {g["id"]: g for g in jl(EV / run / "graded_v21.jsonl")}
            for iid, item in items.items():
                if iid not in answers:
                    continue
                row = check(item, answers[iid], side == "에이전트")
                row["대상"] = side
                g = graded.get(iid) or {}
                row["채점자 판정"] = g.get("최종")
                row["채점자 덧붙임(원문에 없음)"] = [x.get("내용", x) for x in (g.get("LLM") or {}).get("덧붙인 내용") or [] if not x.get("원문에 있음")]
                rows.append(row)
    (EV / "quote_check.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 3) if xs else None

    print("== 답 분류와 평균 원문 일치도 (A형은 본 점수 101문항, A2형 38문항) ==")
    for typ in ("A", "A2"):
        for side in ("기본 AI", "에이전트"):
            sel = [r for r in rows if r["유형"] == typ and r["대상"] == side and (typ == "A2" or r["본문항"])]
            print(f"{typ:2} {side:5} n={len(sel):3}  원문 일치도 {mean(r.get('원문 일치도') for r in sel)}"
                  + (f"  발췌 일치도 {mean(r.get('발췌 일치도') for r in sel)}" if side == "에이전트" else "")
                  + f"  {dict(Counter(r['답 분류'] for r in sel))}")
    print("\n== 조건 누락 (A형 본 점수, '적혀 있지 않다' 제외) × 채점자 판정 ==")
    for side in ("기본 AI", "에이전트"):
        sel = [r for r in rows if r["유형"] == "A" and r["대상"] == side and r["본문항"] and r["답 분류"] not in ("적혀 있지 않다", "빈 답")]
        tab = Counter(("누락" if r.get("조건 누락") else "온전", r["채점자 판정"]) for r in sel)
        g4 = sum(1 for r in sel if r.get("조건 누락") and r["gate"] == "G4")
        print(f"{side:5} {dict(sorted(tab.items()))}  (누락 중 G4 이전 치료 {g4})")
    print("\n== 채점자의 '원문에 없는 덧붙임' 표시 × 코드의 '원문과 겹치지 않는 10자 이상 구간' (A·A2형) ==")
    for side in ("기본 AI", "에이전트"):
        sel = [r for r in rows if r["대상"] == side and r["답 분류"] not in ("적혀 있지 않다", "빈 답")]
        t = Counter((bool(r["채점자 덧붙임(원문에 없음)"]), bool(r.get("원문에 없는 구절"))) for r in sel)
        print(f"{side:5} 답 {len(sel)}  채점자 표시 {t[(True, True)] + t[(True, False)]}  코드 표시 {t[(True, True)] + t[(False, True)]}"
              f"  일치율 {round((t[(True, True)] + t[(False, False)]) / len(sel), 3)}")
    return rows


if __name__ == "__main__":
    main()
