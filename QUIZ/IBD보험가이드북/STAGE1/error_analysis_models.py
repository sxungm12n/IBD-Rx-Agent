#!/usr/bin/env python3
"""세 모델 × 두 대상 오답 원인 분류 (API 없음, 저장된 답·채점만, 2026-11-16).

analyze_errors.py(gpt 에이전트, 원인 일부는 손 분류)를 모든 모델·대상으로 넓힌 코드 규칙 판이다.
사람 판단 없이 다시 계산되며, gpt 에이전트에서 손 분류(오답원인분류_에이전트.md)와 얼마나 같은지로 규칙을 확인한다.

문항마다 '맞음'이 아닌 답에 원인 하나를 붙인다 (위 규칙부터 먼저 적용).
  A·A2형 (gpt-6-sol 채점 v2.1 첫 회)
    에이전트
      1 검색: 근거 쪽 없음        핵심 쪽이 검색된 5쪽에 없음 (analyze_errors.key_pages 규칙 + 검사 하한은 체크리스트 쪽, 처방 기간은 투약간격·고시 쪽)
      2 읽기: 쪽이 있는데 '적혀 있지 않다'
      3 읽기: 다른 기준을 옮김    활성도 문항에 '감소'(투여 지속·유지 평가 기준)를 답함
      4 답변: 조건 축약          quote_check.check의 조건 누락(내약성·금기·부작용·중단), 또는 채점 이유에 금기·내약성 누락
      5 답변: 원문에 없는 덧붙임  채점자가 '원문에 없음'으로 표시
      6 평가 시점                채점 이유에 '시점'
      7 필수 요소 일부 빠뜨림     채점 이유에 빠짐·누락·밝히지 않음
      8 수치·비교                채점 이유에 숫자·이상·초과·미만·감소·점
      9 그 밖의 혼동
    기본 AI
      1 모름: '적혀 있지 않다'
      2 기준 혼동: TNF·생물학제제   이전 치료 문항에서 TNF·종양괴사 언급
      3 지어냄: 원문에 없는 덧붙임
      4~7 평가 시점 → 필수 요소 일부 빠뜨림 → 수치·비교 → 그 밖의 혼동 (에이전트 6~9와 같은 규칙)
  C형 (코드 채점): 방향(허용 아니오→예 / 막음 예→아니오 / 미룸 →판단 불가 / 단정 판단 불가→예·아니오) × 결정 기준.
       에이전트는 핵심 쪽 검색 여부, 기본 AI는 이유의 TNF·생물학제제 언급을 함께 센다.
  D형 (코드 채점): 사건 단위(약 하나 = 사건 하나)
       빠뜨림(그 약 고시 쪽 검색 O/X), 잘못 넣음(제외 이유가 안전 조건인지, 근거 쪽 검색 O/X: 검사 수치면 체크리스트 쪽, 그 밖은 고시 쪽),
       해외·가이드북 밖 약, 이미 실패한 약, 알아보지 못한 이름(NAME_VARIANTS 표로 가이드북 약·해외 약을 추정, 채점은 그대로).
       참고값: 표기 변형을 인정했을 때의 완전 일치 문항 수 (score_cases.py는 바꾸지 않음).
  공통 오답: 같은 문항을 세 모델 에이전트가 모두 틀린 경우 → 모델보다 문항·검색 쪽 원인 후보.
결과: eval_out/오답원인_모델별.json, eval_out/오답원인_모델별.md
"""
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eval_a as E  # noqa: E402
import quote_check as Q  # noqa: E402
import risk_analysis as R  # noqa: E402

OUT, EV = HERE / "output", HERE / "eval_out"
MODELS = ["gpt-5.6-terra", "claude-opus-5-5", "qwen3-14b-bf16"]
SHORT = {"gpt-5.6-terra": "gpt", "claude-opus-5-5": "Opus", "qwen3-14b-bf16": "Qwen"}
TNF = re.compile(r"TNF|종양괴사")
TNF_BIO = re.compile(r"TNF|종양괴사|생물학제제")
TIME = re.compile(r"시점")
NUM = re.compile(r"숫자|수치|값|이상|초과|미만|이하|감소|\d+\s*점|%")
OMIT = re.compile(r"빠졌|빠뜨|빠져|누락|밝히지|언급하지|없습니다\.?$")
RESP_OMIT = re.compile(r"(금기|내약성|불내성)[^.]{0,40}(빠|누락)|(빠|누락)[^.]{0,20}(금기|내약성|불내성)")
LAB = re.compile(r"Hb|ANC|ALC|헤모글로빈|호중구|림프구")
DCHECK = {"Filgotinib": 49, "Upadacitinib": 52, "Tofacitinib": 55, "Ozanimod": 57}  # simulate_retrieval.DCHECK와 같음
SAFETY = re.compile(r"Hb|ANC|ALC|헤모글로빈|호중구|림프구|65세|고령|심혈관|악성|심근경색|금기")

# ---- analyze_errors.py와 같은 쪽 규칙 (그 파일은 import하면 결과 파일을 다시 쓰므로 옮겨 둠) ----
CRIT_GATES = {"G3", "G4", "E", "G5", "전체", "W"}
DPAGE = {("Infliximab", "CD"): [35, 38], ("Infliximab", "UC"): [36, 39], ("Infliximab", "GIBD"): [37],
         ("Adalimumab", "CD"): [40], ("Adalimumab", "UC"): [41], ("Adalimumab", "GIBD"): [42],
         ("Golimumab", "UC"): [43], ("Vedolizumab", "CD"): [44], ("Vedolizumab", "UC"): [45],
         ("Ustekinumab", "CD"): [46], ("Ustekinumab", "UC"): [47], ("Filgotinib", "UC"): [48, 49],
         ("Upadacitinib", "CD"): [50, 52], ("Upadacitinib", "UC"): [51, 52],
         ("Tofacitinib", "UC"): [54, 55], ("Ozanimod", "UC"): [56, 57]}


def pages(sp):
    out = []
    for a, b in re.findall(r"(\d+)(?:~(\d+))?", sp or ""):
        out += list(range(int(a), int(b or a) + 1))
    return out


CHECKLIST = {49, 52, 53, 55, 57}  # 투여 전 체크리스트 쪽 (simulate_retrieval.CHECK와 같음)


def key_pages(it):
    """analyze_errors.key_pages + 두 가지를 좁힘 (손 분류 '검색 실패'와 맞추려고):
    검사 하한 문항(A G6, C 결정 기준 '검사 하한')은 체크리스트 쪽만, 처방 기간(A2 L)은 투약간격(28~30)·고시 쪽만 핵심 쪽."""
    sp = [p for p in pages(it.get("source_page")) if p != 34]
    crit = [p for p in sp if p >= 35]
    g = it["gate"]
    lab = it["type"] == "C" and it["answer"]["채점"].get("결정 기준") == "검사 하한"
    if g == "G6" or lab:
        return [p for p in sp if p in CHECKLIST] or crit or sp
    if g == "L":
        return [p for p in sp if 28 <= p <= 30 or p >= 35] or sp
    if it["type"] == "C" or g in CRIT_GATES or it["기준"].startswith("금기(체크"):
        return crit or sp
    return sp


def jl(p: Path) -> dict:
    return {r["id"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())} if p.exists() else {}


def retrieved(ans):
    return [s["page"] for s in (ans.get("응답") or {}).get("sources", [])]


def gate(it):
    return it["기준"].split("(")[0]


# ---------------- A·A2 ----------------
def classify_text(it, g, ans, agent: bool):
    body = E.answer_body(g["채점 대상"])
    L = g.get("LLM") or {}
    reason = L.get("이유", "")
    added = [x for x in (L.get("덧붙인 내용") or []) if not x.get("원문에 있음")]
    if agent:
        kp = key_pages(it)
        if not any(p in retrieved(ans) for p in kp):
            return "검색: 근거 쪽 없음"
        if E.NOT_WRITTEN.search(body):
            return "읽기: 쪽이 있는데 '적혀 있지 않다'"
        if gate(it) == "활성도" and "감소" in body:
            return "읽기: 다른 기준을 옮김 (지속·유지 기준)"
        row = Q.check(it, {"reply": g["채점 대상"], "응답": ans.get("응답")}, True)
        if row.get("조건 누락"):
            return "답변: 조건 축약"
        if added:
            return "답변: 원문에 없는 덧붙임"
    else:
        if E.NOT_WRITTEN.search(body):
            return "모름: '적혀 있지 않다'"
        if gate(it) == "이전 치료" and TNF.search(body):
            return "기준 혼동: TNF·생물학제제"
        if added:
            return "지어냄: 원문에 없는 덧붙임"
    if agent and RESP_OMIT.search(reason):
        return "답변: 조건 축약"  # quote_check가 못 잡은 바꿔 쓴 축약 (채점 이유에 금기·내약성 누락)
    if TIME.search(reason):
        return "평가 시점"
    if OMIT.search(reason):
        return "필수 요소 일부 빠뜨림"
    if NUM.search(reason):
        return "수치·비교"
    return "그 밖의 혼동"


def text_type(model, prefix, items_file, arm, main_only):
    items = jl(OUT / items_file)
    run = f"{prefix}{arm}_{model}"
    g, a = jl(EV / run / "graded_v21.jsonl"), jl(EV / run / "answers.jsonl")
    rows = []
    for i, it in items.items():
        if main_only and E.is_checklist(it):
            continue
        if i not in g or g[i]["최종"] == "맞음":
            continue
        rows.append({"id": i, "기준": gate(it), "판정": g[i]["최종"],
                     "원인": classify_text(it, g[i], a.get(i, {}), arm == "agent"),
                     "답": E.answer_body(g[i]["채점 대상"])[:160], "채점 이유": (g[i].get("LLM") or {}).get("이유", "")[:200]})
    return rows


# ---------------- C ----------------
def direction(gold, ans):
    if gold == "아니오" and ans == "예":
        return "허용 (아니오→예)"
    if gold == "예" and ans == "아니오":
        return "막음 (예→아니오)"
    if ans == "판단 불가":
        return f"미룸 ({gold}→판단 불가)"
    if gold == "판단 불가":
        return f"단정 (판단 불가→{ans})"
    return f"기타 ({gold}→{ans})"


def c_type(model, arm):
    items = jl(OUT / "c_items.jsonl")
    run = f"c_{arm}_{model}"
    g, a = jl(EV / run / "graded_code.jsonl"), jl(EV / run / "answers.jsonl")
    rows = []
    for i, r in g.items():
        if r["최종"] == "맞음":
            continue
        it = items[i]
        row = {"id": i, "결정 기준": it["answer"]["채점"]["결정 기준"], "방향": direction(r["판정(정답)"], r["판정(답)"]),
               "형식 오류": bool(r.get("형식 오류")), "답": r["채점 대상"][:200]}
        if arm == "agent":
            row["핵심 쪽 검색"] = any(p in retrieved(a.get(i, {})) for p in key_pages(it))
        else:
            row["TNF·생물학제제 언급"] = bool(TNF_BIO.search(r["채점 대상"]))
        rows.append(row)
    return rows


# ---------------- D ----------------
# 채점 코드가 알아보지 못한 이름 → Claude가 하나씩 읽고 정한 대응 (2026-11-16, 사람 검수 전. 분석용, 채점은 바꾸지 않음)
#   가이드북 9개 성분 중 하나로 읽히면 그 성분, 가이드북 밖 실제 약이면 '해외:', 알 수 없으면 None
NAME_VARIANTS = {
    "아다리무맙": "Adalimumab", "아다ليم마브": "Adalimumab", "아다리무스": "Adalimumab",
    "벡도리주맙": "Vedolizumab", "벡로디주맙": "Vedolizumab",
    "우스테키눔브": "Ustekinumab", "우스테킨ум브": "Ustekinumab", "우스테키눔맙": "Ustekinumab", "유스티키마브": "Ustekinumab",
    "유스테킨ум브": "Ustekinumab", "유스테키눔라브": "Ustekinumab",
    "고리무맙": "Golimumab", "고리마브": "Golimumab",
    "토크시티닙": "Tofacitinib", "투파시티닙": "Tofacitinib", "토타시티닙": "Tofacitinib",
    "업다세티닙": "Upadacitinib", "레무시마": "Infliximab",
    "세르토리주맙 페고프": "해외:Certolizumab", "세르토리주맙 페고롤": "해외:Certolizumab",
    "세쿠킨وم맙": "해외:Secukinumab", "세툭시마브": None,
}


def guess_drug(name: str):
    v = NAME_VARIANTS.get(name.strip())
    return v if v and not v.startswith("해외:") else None


def d_type(model, arm):
    items = jl(OUT / "d_items.jsonl")
    run = f"d_{arm}_{model}"
    g, a = jl(EV / run / "graded_code.jsonl"), jl(EV / run / "answers.jsonl")
    ev = collections.Counter()
    rows, lenient = [], 0
    for i, r in g.items():
        it = items[i]
        dis = it["patient"]["dis"]
        ret = set(retrieved(a.get(i, {}))) if arm == "agent" else set()
        reasons = it.get("제외 이유(참고)") or {}
        labs = []
        named = {x: guess_drug(x) for x in R.as_list(r.get("알아보지 못한 이름"))}
        renamed = {d for d in named.values() if d}
        # 표기 변형을 인정했을 때의 완전 일치 (참고값)
        guide = (set(R.as_list(r["인정(답)"])) - set(R.as_list(r["해외·가이드북 밖 약"])) - set(R.as_list(r["범위 밖 약"]))) | renamed
        if guide == set(it["answer"]["채점"]["인정"]) and not R.as_list(r["해외·가이드북 밖 약"]) and not R.as_list(r["범위 밖 약"]) \
                and all(named.values()) and not r.get("형식 오류"):
            lenient += 1
        for dr in R.as_list(r["빠뜨림"]):
            if dr in renamed:
                lab = "빠뜨림 · 실제로는 이름 표기 오류"
            elif arm == "agent":
                hit = any(p in ret for p in DPAGE.get((dr, dis), []))
                lab = "빠뜨림 · 고시 쪽 있음 (읽기)" if hit else "빠뜨림 · 고시 쪽 없음 (검색)"
            else:
                lab = "빠뜨림"
            ev[lab] += 1
            labs.append(f"{lab}: {dr}")
        for dr in R.as_list(r["가이드북 약 중 틀리게 넣음"]):
            why = str(reasons.get(dr, "")) if isinstance(reasons, dict) else str(reasons)
            kind = "안전 조건" if SAFETY.search(why) else "급여 기준·범위"
            if arm == "agent":
                # 검사 수치(Hb·ANC·ALC) 때문에 빠져야 하는 약은 체크리스트 쪽, 그 밖에는 고시 쪽이 근거 쪽
                need = [DCHECK[dr]] if LAB.search(why) and dr in DCHECK else DPAGE.get((dr, dis), [])
                hit = any(p in ret for p in need)
                lab = f"잘못 넣음 · {kind} · {'근거 쪽 있음' if hit else '근거 쪽 없음'}"
            else:
                lab = f"잘못 넣음 · {kind}"
            ev[lab] += 1
            labs.append(f"{lab}: {dr}")
        for k, lab in (("해외·가이드북 밖 약", "해외·가이드북 밖 약"), ("알아보지 못한 이름", "알아보지 못한 이름"),
                       ("범위 밖 약", "범위 밖 전통 치료제")):
            for x in R.as_list(r.get(k)):
                if k == "알아보지 못한 이름" and str(NAME_VARIANTS.get(x.strip()) or "").startswith("해외:"):
                    lab2 = "알아보지 못한 이름 → 해외 약"
                    ev[lab2] += 1
                    labs.append(f"{lab2}: {x}")
                    continue
                if k == "알아보지 못한 이름" and named.get(x):
                    lab2 = f"알아보지 못한 이름 → {named[x]}로 추정"
                else:
                    lab2 = lab
                ev[lab2 if k != "알아보지 못한 이름" or not named.get(x) else "알아보지 못한 이름 (가이드북 약으로 추정 가능)"] += 1
                labs.append(f"{lab2}: {x}")
        if r.get("이미 실패한 약 다시 씀"):
            ev["이미 실패한 약 재사용"] += 1
            labs.append("이미 실패한 약 재사용")
        if r["최종"] != "맞음":
            rows.append({"id": i, "질환": dis, "사건": labs, "답": r["채점 대상"][:200]})
    ev["(참고) 표기 변형을 인정한 완전 일치 문항"] = lenient
    ev["(참고) 지금 규칙의 완전 일치 문항"] = sum(1 for r in g.values() if r["최종"] == "맞음")
    return rows, dict(ev)


def main() -> int:
    res = {"모델": MODELS, "A": {}, "A2": {}, "C": {}, "D": {}}
    for m in MODELS:
        for arm in ("llm", "agent"):
            k = f"{SHORT[m]} {('기본 AI' if arm == 'llm' else '에이전트')}"
            res["A"][k] = text_type(m, "", "a_items.jsonl", arm, True)
            res["A2"][k] = text_type(m, "a2_", "a2_items.jsonl", arm, False)
            res["C"][k] = c_type(m, arm)
            rows, ev = d_type(m, arm)
            res["D"][k] = {"문항": rows, "사건": ev}

    # 공통 오답 (세 모델 에이전트가 모두 틀린 문항)
    common = {}
    for T in ("A", "A2", "C"):
        sets = [{r["id"] for r in res[T][f"{SHORT[m]} 에이전트"]} for m in MODELS]
        common[T] = sorted(set.intersection(*sets))
    sets = [{r["id"] for r in res["D"][f"{SHORT[m]} 에이전트"]["문항"]} for m in MODELS]
    common["D"] = sorted(set.intersection(*sets))
    res["세 모델 에이전트 공통 오답"] = common

    # gpt 에이전트 손 분류와 대조 (오답원인분류_에이전트.md, A형 본 점수)
    gpt_a = collections.Counter(r["원인"] for r in res["A"]["gpt 에이전트"])
    res["gpt 에이전트 손 분류 대조 (A 본 점수)"] = {
        "손 분류": {"검색": 6, "조건 축약": 16, "다른 칸에 답함(개념 혼동)": 5, "비교 방향": 1},
        "코드 분류": dict(gpt_a)}

    (EV / "오답원인_모델별.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------- 보고서 ----------------
    cols = [f"{SHORT[m]} {s}" for s in ("기본 AI", "에이전트") for m in MODELS]
    L = ["# 오답 원인 · 세 모델 × 두 대상 (API 없음, 코드 규칙)", "",
         "- 대상: '맞음'이 아닌 답 (A형은 본 점수 101문항). 원인은 위에서부터 먼저 맞는 규칙 하나 (`error_analysis_models.py` 머리말).",
         "- 세 모델 에이전트는 같은 5쪽(gpt가 검색한 쪽)을 받았다 → '검색: 근거 쪽 없음'은 세 모델에 같은 조건이다.", ""]
    for T, title in (("A", "A형 본 점수 (101)"), ("A2", "A2형 (38)")):
        cats = []
        for c in cols:
            for r in res[T][c]:
                if r["원인"] not in cats:
                    cats.append(r["원인"])
        L += [f"## {title} · 원인별 문항 수", "", "| 원인 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
        cnt = {c: collections.Counter(r["원인"] for r in res[T][c]) for c in cols}
        for cat in cats:
            L.append(f"| {cat} | " + " | ".join(str(cnt[c][cat] or "") for c in cols) + " |")
        L.append("| **오답 합계** | " + " | ".join(str(len(res[T][c])) for c in cols) + " |")
        L.append("")
    # C
    L += ["## C형 (198) · 오답 방향", "", "| 방향 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    dirs = []
    for c in cols:
        for r in res["C"][c]:
            if r["방향"] not in dirs:
                dirs.append(r["방향"])
    for dname in dirs:
        L.append(f"| {dname} | " + " | ".join(str(sum(1 for r in res['C'][c] if r['방향'] == dname) or "") for c in cols) + " |")
    L.append("| **오답 합계** | " + " | ".join(str(len(res["C"][c])) for c in cols) + " |")
    L.append("| 에이전트: 핵심 쪽 없이 틀림 | " + " | ".join(
        str(sum(1 for r in res["C"][c] if r.get("핵심 쪽 검색") is False)) if "에이전트" in c else "–" for c in cols) + " |")
    L.append("| 기본 AI: 이유에 TNF·생물학제제 | " + " | ".join(
        str(sum(1 for r in res["C"][c] if r.get("TNF·생물학제제 언급"))) if "기본 AI" in c else "–" for c in cols) + " |")
    L += ["", "### C형 · 결정 기준별 오답 수", "", "| 결정 기준 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    crits = sorted({r["결정 기준"] for c in cols for r in res["C"][c]})
    for cr in crits:
        L.append(f"| {cr} | " + " | ".join(str(sum(1 for r in res['C'][c] if r['결정 기준'] == cr) or "") for c in cols) + " |")
    # D
    L += ["", "## D형 (37) · 사건 수 (약 하나 = 사건 하나)", "", "| 사건 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    evs = []
    for c in cols:
        for k in res["D"][c]["사건"]:
            if k not in evs:
                evs.append(k)
    for k in evs:
        L.append(f"| {k} | " + " | ".join(str(res['D'][c]['사건'].get(k, '') or '') for c in cols) + " |")
    L.append("| **틀린 문항** | " + " | ".join(str(len(res["D"][c]["문항"])) for c in cols) + " |")
    # 공통
    L += ["", "## 세 모델 에이전트가 모두 틀린 문항", ""]
    for T in ("A", "A2", "C", "D"):
        L.append(f"- {T}형 {len(common[T])}: " + (", ".join(common[T]) if common[T] else "없음"))
    L += ["", "## 규칙 확인: gpt 에이전트 손 분류와 대조 (A 본 점수)", "",
          f"- 손 분류(오답원인분류_에이전트.md): 검색 6 · 조건 축약 16 · 다른 칸에 답함 5 · 비교 방향 1",
          f"- 코드 분류: " + " · ".join(f"{k} {v}" for k, v in gpt_a.most_common()), ""]
    (EV / "오답원인_모델별.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
