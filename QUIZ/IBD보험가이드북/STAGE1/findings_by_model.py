#!/usr/bin/env python3
"""모델별 발견 (API 없음, 저장된 답·채점만, 2026-11-16).

gpt-5.6-terra로 정리한 발견(기준 혼동, 에이전트 오류 원인, 안전 오답)을 같은 규칙으로 다른 모델에도 계산한다.
gpt-5.6-terra 값이 기존 보고서(오답원인분류·인용문원문대조·오답위험도)와 같게 나오는지로 규칙을 확인한다.

규칙 (모두 코드, 사람 판단 없음)
  기준 혼동 (기본 AI)
    A형 '이전 치료' 틀림 답 중 TNF를 언급한 답 (정규식 TNF|종양괴사)
    C형 정답 '예'를 '아니오'로 막은 답 중 이유에 TNF·생물학제제를 언급한 답
    D형 해외·가이드북 밖 약(score_cases 판정)
    A·A2형 채점자가 '원문에 없는 덧붙임'으로 표시한 답 수
  에이전트 오류
    A형 본 점수의 기준별 잃은 점수, 조건 누락(quote_check.check와 같은 규칙: 내약성·금기·부작용·중단)
    D형 빠뜨린 약과 그 약의 고시 쪽이 발췌에 있었는지(analyze_errors.DPAGE와 같은 쪽 표)
    D형 정답 약 중 고시 쪽이 발췌에 없는데도 넣은 약(기억으로 보충)
  안전 오답: risk_analysis.py 규칙
결과: eval_out/모델별발견.json, eval_out/모델별발견.md
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
MODELS = ["gpt-5.6-terra", "claude-opus-5-5"]
TNF = re.compile(r"TNF|종양괴사")
TNF_BIO = re.compile(r"TNF|종양괴사|생물학제제")
DPAGE = {("Infliximab", "CD"): [35, 38], ("Infliximab", "UC"): [36, 39], ("Infliximab", "GIBD"): [37],
         ("Adalimumab", "CD"): [40], ("Adalimumab", "UC"): [41], ("Adalimumab", "GIBD"): [42],
         ("Golimumab", "UC"): [43], ("Vedolizumab", "CD"): [44], ("Vedolizumab", "UC"): [45],
         ("Ustekinumab", "CD"): [46], ("Ustekinumab", "UC"): [47], ("Filgotinib", "UC"): [48, 49],
         ("Upadacitinib", "CD"): [50, 52], ("Upadacitinib", "UC"): [51, 52],
         ("Tofacitinib", "UC"): [54, 55], ("Ozanimod", "UC"): [56, 57]}  # analyze_errors.py와 같음


def jl(p: Path) -> dict:
    return {r["id"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())} if p.exists() else {}


def items(name):
    return jl(OUT / name)


def gate_name(it):
    return it["기준"].split("(")[0]


def model_findings(m: str) -> dict:
    A, A2, C, D = items("a_items.jsonl"), items("a2_items.jsonl"), items("c_items.jsonl"), items("d_items.jsonl")
    f = {"모델": m}

    # ---- 기본 AI: 기준 혼동 ----
    g = jl(EV / f"llm_{m}" / "graded_v21.jsonl")
    prior_wrong = [i for i, it in A.items() if gate_name(it) == "이전 치료" and g.get(i, {}).get("최종") == "틀림"]
    prior_tnf = [i for i in prior_wrong if TNF.search(g[i]["채점 대상"])]
    prior_partial_tnf = [i for i, it in A.items() if gate_name(it) == "이전 치료" and g.get(i, {}).get("최종") == "부분"
                         and TNF.search(g[i]["채점 대상"])]
    cg = jl(EV / f"c_llm_{m}" / "graded_code.jsonl")
    blocked = [i for i, r in cg.items() if r["판정(정답)"] == "예" and r["판정(답)"] == "아니오"]
    blocked_tnf = [i for i in blocked if TNF_BIO.search(r_reason := cg[i]["채점 대상"])]
    dg = jl(EV / f"d_llm_{m}" / "graded_code.jsonl")
    foreign = collections.Counter(x for r in dg.values() for x in R.as_list(r["해외·가이드북 밖 약"]))
    f["기본 AI"] = {
        "A 이전 치료 틀림": len(prior_wrong), "그중 TNF 언급": len(prior_tnf), "A 이전 치료 부분 중 TNF 언급": len(prior_partial_tnf),
        "C 급여 대상을 막음(예→아니오)": len(blocked), "그중 TNF·생물학제제 언급": len(blocked_tnf),
        "D 해외·가이드북 밖 약 사례": sum(1 for r in dg.values() if R.as_list(r["해외·가이드북 밖 약"])),
        "D 해외 약 목록": dict(foreign),
    }
    add = {}
    for typ, run, its in (("A", f"llm_{m}", A), ("A2", f"a2_llm_{m}", A2)):
        gg = jl(EV / run / "graded_v21.jsonl")
        add[typ] = sum(1 for i in its if any(not x.get("원문에 있음") for x in ((gg.get(i) or {}).get("LLM") or {}).get("덧붙인 내용") or []))
    f["기본 AI"]["원문에 없는 덧붙임 표시 답 (A/A2)"] = add
    a2g = jl(EV / f"a2_llm_{m}" / "graded_v21.jsonl")
    f["기본 AI"]["A2 '적혀 있지 않다' 답"] = sum(1 for r in a2g.values() if E.NOT_WRITTEN.search(E.answer_body(r["채점 대상"])))

    # ---- 에이전트: 오류 원인 ----
    ga = jl(EV / f"agent_{m}" / "graded_v21.jsonl")
    ans = jl(EV / f"agent_{m}" / "answers.jsonl")
    main = [i for i, it in A.items() if not E.is_checklist(it)]
    lost = collections.Counter()
    for i in main:
        lost[gate_name(A[i])] += 1 - E.SCORE[ga[i]["최종"]]
    omit = []
    for i in main:
        row = Q.check(A[i], ans[i], True)
        if row.get("답 분류") in ("적혀 있지 않다", "빈 답"):
            continue
        if row.get("조건 누락"):
            omit.append((i, ga[i]["최종"]))
    f["에이전트"] = {
        "A 맞음/부분/틀림": dict(collections.Counter(ga[i]["최종"] for i in main)),
        "A 기준별 잃은 점수": {k: round(v, 1) for k, v in lost.most_common()},
        "A 조건 누락(축약)": len(omit), "그중 채점 '부분'": sum(1 for _, v in omit if v == "부분"),
    }
    da = jl(EV / f"d_agent_{m}" / "graded_code.jsonl")
    dans = jl(EV / f"d_agent_{m}" / "answers.jsonl")
    miss, miss_noret, filled = collections.Counter(), 0, collections.Counter()
    for i, r in da.items():
        dis = D[i]["patient"]["dis"]
        ret = {s["page"] for s in dans[i]["응답"]["sources"]}
        for dr in R.as_list(r["빠뜨림"]):
            miss[dr] += 1
            if not any(p in ret for p in DPAGE.get((dr, dis), [])):
                miss_noret += 1
        written = set(R.as_list(r.get("인정(답)", [])))
        for dr in set(D[i]["answer"]["채점"]["인정"]) & written:
            if not any(p in ret for p in DPAGE.get((dr, dis), [])):
                filled[dr] += 1
    f["에이전트"].update({
        "D 빠뜨린 약": sum(miss.values()), "그중 고시 쪽 미검색": miss_noret, "D 빠뜨린 약 목록": dict(miss.most_common()),
        "D 고시 쪽 없이 맞게 넣은 정답 약": sum(filled.values()), "그 약 목록": dict(filled.most_common()),
        "D 실패한 약 재사용": sum(1 for r in da.values() if r.get("이미 실패한 약 다시 씀")),
    })
    ca = jl(EV / f"c_agent_{m}" / "graded_code.jsonl")
    f["에이전트"]["C 오답 (정답→답)"] = dict(collections.Counter(f"{r['판정(정답)']}→{r['판정(답)']}" for r in ca.values() if r["최종"] != "맞음"))
    a2a = jl(EV / f"a2_agent_{m}" / "graded_v21.jsonl")
    f["에이전트"]["A2 맞음/부분/틀림"] = dict(collections.Counter(r["최종"] for r in a2a.values()))
    addag = {}
    for typ, run, its in (("A", f"agent_{m}", A), ("A2", f"a2_agent_{m}", A2)):
        gg = jl(EV / run / "graded_v21.jsonl")
        addag[typ] = sum(1 for i in its if any(not x.get("원문에 있음") for x in ((gg.get(i) or {}).get("LLM") or {}).get("덧붙인 내용") or []))
    f["에이전트"]["원문에 없는 덧붙임 표시 답 (A/A2)"] = addag

    # ---- 안전 오답 ----
    saf = {}
    for arm, side in (("llm", "기본 AI"), ("agent", "에이전트")):
        c = [r for r in R.c_rows(side, f"{arm}_{m}") if r["위험도"] == R.LEVELS[0]]
        d = [r for r in R.d_rows(side, f"{arm}_{m}") if r["위험도"] == R.LEVELS[0]]
        saf[side] = {"C": len(c), "D": len(d), "C 문항": [r["id"] for r in c], "D 문항": [r["id"] for r in d]}
    f["안전 오답"] = saf
    return f


def main() -> int:
    res = [model_findings(m) for m in MODELS]
    (EV / "모델별발견.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# 모델별 발견 (API 없음, 같은 규칙)", ""]
    for f in res:
        L += [f"## {f['모델']}", "", "```json", json.dumps({k: v for k, v in f.items() if k != "모델"}, ensure_ascii=False, indent=1), "```", ""]
    (EV / "모델별발견.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
