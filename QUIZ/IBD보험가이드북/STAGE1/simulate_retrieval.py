#!/usr/bin/env python3
"""검색 개선 시뮬레이션 (API 없음).

에이전트가 실제로 가져온 5쪽(answers.jsonl의 sources)에 규칙으로 쪽을 덧붙였을 때
정답 근거 쪽이 얼마나 들어오는지와 발췌 길이가 얼마나 늘어나는지를 계산한다.
답을 다시 받지 않으므로 '근거 쪽이 들어온다'까지만 보여 준다.

규칙은 가이드북 쪽 메타데이터(약·질환·제목)만 쓰고, 문항 정답은 쓰지 않는다.
  A (딸린 쪽): 가져온 고시 쪽(p.35~57)마다 같은 약·질환의 체크리스트 쪽과 투약간격 쪽(p.28~30)을 붙임
  B (A + 질문 라우팅): 질문 대괄호의 약·질환(D형은 환자 질환의 9개 성분 전체)에 맞는 쪽을 붙이고 A 적용
결과: eval_out/simulate_retrieval.json, 콘솔 요약
"""
import json, re, collections
from pathlib import Path

S1 = Path(__file__).resolve().parent
CORPUS = S1.parents[2] / "data/RAG/IBD_insurance_guide_2024.jsonl"
OUT, EV = S1 / "output", S1 / "eval_out"

def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

# ---- 쪽 메타데이터 (쪽 단위로 합침) ----
PG = {}
for r in jl(CORPUS):
    m = PG.setdefault(r["page"], {"drugs": set(), "dis": set(), "title": r["title"], "chars": 0})
    m["drugs"] |= set(r.get("drugs") or []); m["dis"] |= set(r.get("disease") or []); m["chars"] += len(r["text"])
CHECK = {p for p, m in PG.items() if "체크리스트" in m["title"]}
CRIT = {p for p in PG if 35 <= p <= 57 and p not in CHECK}
INTERVAL = {28, 29, 30}
DRUGS9 = ["Infliximab", "Adalimumab", "Golimumab", "Vedolizumab", "Ustekinumab",
          "Tofacitinib", "Filgotinib", "Upadacitinib", "Ozanimod"]

def share(p, q):
    return PG[p]["drugs"] & PG[q]["drugs"] and (PG[p]["dis"] & PG[q]["dis"])

def rule_a(pages):
    out = set(pages)
    for p in pages:
        if p in CRIT:
            out |= {q for q in CHECK | INTERVAL if share(p, q)}
    return out

DIS_KW = [("크론", "CD"), ("궤양성", "UC"), ("베체트", "GIBD")]

def route(it):
    """질문(D형은 환자)에서 약·질환을 읽어 붙일 쪽."""
    if it["type"] == "D":
        dis = it["patient"]["dis"]
        return {p for p in CRIT if PG[p]["dis"] & {dis} and PG[p]["drugs"] & set(DRUGS9)}
    m = re.match(r"\[([^\]]+)\]", it["question"])
    head = m.group(1) if m else ""
    dis = {c for k, c in DIS_KW if k in head}
    drugs = {d for d in set().union(*(PG[p]["drugs"] for p in PG)) if d.lower() in head.lower()}
    if not drugs or not dis:
        return set()
    cand = {p for p in PG if PG[p]["drugs"] & drugs and PG[p]["dis"] & dis and len(PG[p]["drugs"]) <= 4}
    crit = {p for p in cand if p in CRIT}
    return crit or cand                         # 고시 쪽이 있으면 고시 쪽, 없으면(MTX 등) 약 설명 쪽

def rule_b(it, pages):
    return rule_a(set(pages) | route(it))

# ---- 오답 분석에서 '근거 쪽을 못 가져옴'으로 분류한 문항과 필요한 쪽 (오답원인분류_에이전트.md) ----
NEED = {"A-MTX-IBD-G7": {19}, "A-IFX-IV-UC-adult-E": {36}, "A-IFX-IV-UC-ped-E": {36}, "A-IFX-IV-GIBD-E": {37},
        "A-FIL-UC-G6-hb": {49}, "A-FIL-UC-G6-alc": {49}, "A-UPA-UC-G6-hb": {52},
        "A2-ADA-CD-adult-L": {28}, "A2-ADA-CD-ped-L": {28}, "A2-ADA-UC-L": {28}, "A2-ADA-GIBD-L": {28},
        "C-FIL-UC-anc-low": {49}, "C-FIL-UC-alc-low": {49}, "C-UPA-UC-hb-low": {52}, "C-UPA-UC-anc-low": {52},
        "C-UPA-UC-alc-low": {52},
        "C-IFX-SC-CD-adult-base": {29}, "C-IFX-SC-UC-adult-base": {29}, "C-IFX-SC-UC-adult-prior-intol": {29}}
DPAGE = {("Infliximab", "CD"): {35, 38}, ("Infliximab", "UC"): {36, 39}, ("Infliximab", "GIBD"): {37},
         ("Adalimumab", "CD"): {40}, ("Adalimumab", "UC"): {41}, ("Adalimumab", "GIBD"): {42},
         ("Golimumab", "UC"): {43}, ("Vedolizumab", "CD"): {44}, ("Vedolizumab", "UC"): {45},
         ("Ustekinumab", "CD"): {46}, ("Ustekinumab", "UC"): {47}, ("Filgotinib", "UC"): {48},
         ("Upadacitinib", "CD"): {50}, ("Upadacitinib", "UC"): {51}, ("Tofacitinib", "UC"): {54},
         ("Ozanimod", "UC"): {56}}
DCHECK = {"Filgotinib": 49, "Upadacitinib": 52, "Tofacitinib": 55, "Ozanimod": 57}

def pages_of(sp):
    out = []
    for a, b in re.findall(r"(\d+)(?:~(\d+))?", sp or ""):
        out += list(range(int(a), int(b or a) + 1))
    return set(out)

SETS = [("A", "a_items", "agent_gpt-5.6-terra", "graded_v21.jsonl"),
        ("A2", "a2_items", "a2_agent_gpt-5.6-terra", "graded_v21.jsonl"),
        ("C", "c_items", "c_agent_gpt-5.6-terra", "graded_code.jsonl"),
        ("D", "d_items", "d_agent_gpt-5.6-terra", "graded_code.jsonl")]

def covered(need, got, mode="all"):
    return need <= got if mode == "all" else bool(need & got)

res = {"오답(검색 실패) 복구": {}, "전체 핵심 쪽 포함률": {}, "발췌 크기": {}, "D형": {}}
size = collections.defaultdict(lambda: collections.defaultdict(list))
cov = collections.defaultdict(lambda: collections.Counter())
d_detail = []
for T, itf, d, gf in SETS:
    items = {i["id"]: i for i in jl(OUT / f"{itf}.jsonl")}
    ans = {a["id"]: a for a in jl(EV / d / "answers.jsonl")}
    gr = {g["id"]: g for g in jl(EV / d / gf)}
    for iid, it in items.items():
        base = {s["page"] for s in ans[iid]["응답"]["sources"]}
        variants = {"현재": base, "규칙 A": rule_a(base), "규칙 B": rule_b(it, base)}
        for k, v in variants.items():
            size[T][k].append((len(v), sum(PG[p]["chars"] for p in v)))
        # 핵심 쪽 정의 (문항 정답이 아니라 문항 종류로 정함)
        if T == "D":
            dis = it["patient"]["dis"]
            drugs = it["answer"]["채점"]["인정"]
            need = set().union(*[DPAGE.get((x, dis), set()) for x in drugs]) if drugs else set()
            lab = any(k in it["patient"] for k in ("Hb", "ANC", "ALC"))
            for k, v in variants.items():
                hit = sum(bool(DPAGE.get((x, dis), set()) & v) for x in drugs)
                cov[(T, k)]["정답 약"] += len(drugs); cov[(T, k)]["정답 약 쪽 있음"] += hit
                cov[(T, k)]["문항"] += 1
                cov[(T, k)]["모든 정답 약 쪽 있음"] += all(DPAGE.get((x, dis), set()) & v for x in drugs)
            g = gr[iid]
            miss = g.get("빠뜨림", [])
            d_detail.append({"id": iid, "빠뜨림": miss, **{k: [x for x in miss if not DPAGE.get((x, dis), set()) & v] for k, v in variants.items()},
                             "UPA 체크리스트(52)": {k: 52 in v for k, v in variants.items()} if "Upadacitinib" in g.get("가이드북 약 중 틀리게 넣음", []) else None})
            continue
        sp = pages_of(it.get("source_page"))
        lab = it["gate"] == "G6" or it["기준"].startswith("금기(체크") or it["gate"] == "검사 하한"
        if lab:
            key, kind = sp & CHECK, "검사 하한·체크리스트"
        elif T == "C" or it["gate"] in {"G3", "G4", "E", "G5", "W"}:
            key, kind = sp & CRIT, "급여 기준(고시 쪽)"
        else:
            continue
        if not key:
            continue
        for k, v in variants.items():
            cov[(T, kind, k)]["문항"] += 1
            cov[(T, kind, k)]["포함"] += covered(key, v, "any")
    # 오답 복구
for T, itf, d, gf in SETS[:3]:
    items = {i["id"]: i for i in jl(OUT / f"{itf}.jsonl")}
    ans = {a["id"]: a for a in jl(EV / d / "answers.jsonl")}
    for iid, need in NEED.items():
        if iid not in items:
            continue
        base = {s["page"] for s in ans[iid]["응답"]["sources"]}
        res["오답(검색 실패) 복구"][iid] = {"필요 쪽": sorted(need), "현재": need <= base,
                                       "규칙 A": need <= rule_a(base), "규칙 B": need <= rule_b(items[iid], base)}

# ---- 출력 ----
print("== 검색 실패로 분류한 오답: 필요한 쪽이 들어오는가")
rows = res["오답(검색 실패) 복구"]
for k in ("현재", "규칙 A", "규칙 B"):
    print(f"  {k}: {sum(r[k] for r in rows.values())} / {len(rows)}")
for iid, r in rows.items():
    print(f"   {iid:<34} 필요 {r['필요 쪽']}  A={'O' if r['규칙 A'] else 'X'} B={'O' if r['규칙 B'] else 'X'}")

print("\n== 전체 문항: 핵심 쪽 포함률 (오답만이 아니라 전체)")
for key, c in sorted(cov.items(), key=lambda x: str(x[0])):
    if key[0] == "D":
        continue
    print(f"  {key[0]:<3} {key[1]:<16} {key[2]:<6} {c['포함']}/{c['문항']}")
print("\n== D형")
for k in ("현재", "규칙 A", "규칙 B"):
    c = cov[("D", k)]
    print(f"  {k:<6} 정답 약 고시 쪽 {c['정답 약 쪽 있음']}/{c['정답 약']} ({c['정답 약 쪽 있음']/c['정답 약']:.2f}), "
          f"모든 정답 약 쪽이 들어온 문항 {c['모든 정답 약 쪽 있음']}/{c['문항']}")
lost = {k: sum(len(r[k]) for r in d_detail) for k in ("현재", "규칙 A", "규칙 B")}
print(f"  빠뜨린 약 43건 중 쪽이 여전히 없는 것: {lost}")
up = [r["UPA 체크리스트(52)"] for r in d_detail if r["UPA 체크리스트(52)"]]
print(f"  Upadacitinib 잘못 넣은 문항({len(up)}): p.52 포함 " + ", ".join(f"{k} {sum(u[k] for u in up)}" for k in ("현재", "규칙 A", "규칙 B")))

print("\n== 발췌 크기 (문항당 평균 쪽 수 / 글자 수)")
for T in ("A", "A2", "C", "D"):
    s = " | ".join(f"{k} {sum(a for a, _ in v)/len(v):.1f}쪽 {sum(b for _, b in v)/len(v):,.0f}자"
                   for k, v in size[T].items())
    print(f"  {T:<3} {s}")

res["전체 핵심 쪽 포함률"] = {" / ".join(k): dict(v) for k, v in cov.items()}
res["발췌 크기"] = {T: {k: {"평균 쪽": round(sum(a for a, _ in v)/len(v), 1), "평균 글자": round(sum(b for _, b in v)/len(v))}
                     for k, v in size[T].items()} for T in size}
res["D형"] = d_detail
(EV / "simulate_retrieval.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
