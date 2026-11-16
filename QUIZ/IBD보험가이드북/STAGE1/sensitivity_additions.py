#!/usr/bin/env python3
"""채점 민감도: '원문에 없는 덧붙임은 틀림' 규칙을 끄면 점수가 어떻게 바뀌나 (API 없음, 저장된 채점 결과만 사용).
  (a) 좁게: 필수 요소를 모두 맞히고 덧붙임 때문에만 틀림인 답 → 맞음
  (b) 넓게: 원문에 없는 덧붙임이 있는 모든 답을 요소만으로 다시 판정 (모두 맞음→맞음, 일부→부분, 없음→틀림), 원래보다 낮추지 않음
"""
import json
from pathlib import Path
S1 = Path(__file__).resolve().parent
OUT, EV = S1 / "output", S1 / "eval_out"
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
SC = {"맞음": 1, "부분": .5, "틀림": 0}
items = {i["id"]: i for i in jl(OUT / "a_items.jsonl") + jl(OUT / "a2_items.jsonl")}

def regrade(g, mode):
    v, L = g["최종"], g.get("LLM") or {}
    bad = [x for x in L.get("덧붙인 내용") or [] if not x.get("원문에 있음")]
    els = L.get("요소") or []
    if v == "맞음" or not bad or not els:
        return v
    n, k = len(els), sum(bool(e.get("맞음")) for e in els)
    if mode == "a":
        return "맞음" if k == n else v
    new = "맞음" if k == n else ("부분" if k else "틀림")
    return new if SC[new] > SC[v] else v

rows = []
for arm, a, a2 in [("기본 AI", "llm_gpt-5.6-terra", "a2_llm_gpt-5.6-terra"), ("에이전트", "agent_gpt-5.6-terra", "a2_agent_gpt-5.6-terra")]:
    g = {x["id"]: x for x in jl(EV / a / "graded_v21.jsonl") + jl(EV / a2 / "graded_v21.jsonl")}
    sets = {"A 본 점수": [i for i in g if i.startswith("A-") and not items[i]["기준"].startswith("금기")],
            "A2": [i for i in g if i.startswith("A2-")]}
    for name, ids in sets.items():
        r = {"대상": arm, "유형": name, "문항": len(ids)}
        for mode, lab in (("orig", "원래"), ("a", "(a) 좁게"), ("b", "(b) 넓게")):
            vs = {i: (g[i]["최종"] if mode == "orig" else regrade(g[i], mode)) for i in ids}
            r[lab] = round(sum(SC[v] for v in vs.values()) / len(ids), 3)
            if mode != "orig":
                r[lab + " 바뀐 문항"] = [i for i in ids if vs[i] != g[i]["최종"]]
        rows.append(r)
for r in rows:
    print(f"{r['대상']:<5} {r['유형']:<7} n={r['문항']:<4} 원래 {r['원래']:.3f}  (a) {r['(a) 좁게']:.3f} [{len(r['(a) 좁게 바뀐 문항'])}]  (b) {r['(b) 넓게']:.3f} [{len(r['(b) 넓게 바뀐 문항'])}]")
for name in ("A 본 점수", "A2"):
    b, e = [r for r in rows if r["유형"] == name]
    print(f"차이 {name}: 원래 {e['원래']-b['원래']:+.3f}  (a) {e['(a) 좁게']-b['(a) 좁게']:+.3f}  (b) {e['(b) 넓게']-b['(b) 넓게']:+.3f}")
for r in rows:
    if r["(b) 넓게 바뀐 문항"]:
        print(r["대상"], r["유형"], "(b) 바뀐 문항:", r["(b) 넓게 바뀐 문항"])
(EV / "sensitivity_additions.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
