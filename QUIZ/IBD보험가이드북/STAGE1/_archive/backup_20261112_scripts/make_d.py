#!/usr/bin/env python3
"""STAGE1 — D형: 환자 사례 약제 선택 문항 (2026-11-11).

"이 환자에게 다음 약 중 급여가 인정되는 약과 제외되는 약(이유)을 모두 쓰시오."
- 후보는 생물학제제·소분자제제 9개 성분으로 고정한다 (질문에 목록을 준다 → 약 이름 채점이 쉬움).
- 정답은 코드가 A형 채점 열쇠(= 가이드북 CSV 기준)로 환자를 약마다 대입해 계산한다. LLM 미사용, OpenAI API 호출 없음.
- 약은 성분 단위로 묻는다. 정맥주사·피하주사의 시작 기준이 같기 때문 (예외: 소아 궤양성 대장염은 Infliximab 정맥주사만 → 이유에 표시).
- 해당 없음 근거 (가이드북 원문):
    p.23 누공성 크론병: Humira·Stelara·Kynteles '해당 없음' / 소아: Stelara·Kynteles '소아 해당 없음'
    p.24 Upadacitinib CD: 누공성 크론병·소아 해당 없음
    p.26 소아 UC: Remicade만 PUCAI>45, Remsima SC·Humira·Simponi·Kynteles·Stelara '소아 해당 없음' / p.27 소분자 4종 소아 해당 없음
    Golimumab·Tofacitinib·Filgotinib·Ozanimod: 궤양성 대장염만 / 장형 베체트: Infliximab·Adalimumab만
사용: python3 STAGE1/make_d.py → output/d_items.jsonl, output/d_summary.json, output/d_review.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
DRUGS = ["Infliximab", "Adalimumab", "Golimumab", "Vedolizumab", "Ustekinumab", "Tofacitinib", "Filgotinib", "Upadacitinib", "Ozanimod"]
JAK = {"Tofacitinib", "Filgotinib", "Upadacitinib"}

# 환자 유형 → 성분별 적용 행 (없으면 제외 사유)
ROW = {
    ("CD", "adult"): {"Infliximab": "IFX-IV-CD-adult", "Adalimumab": "ADA-CD-adult", "Vedolizumab": "VEDO-IV-CD", "Ustekinumab": "UST-CD", "Upadacitinib": "UPA-CD"},
    ("CD", "ped"): {"Infliximab": "IFX-IV-CD-ped", "Adalimumab": "ADA-CD-ped"},
    ("CD", "fistula"): {"Infliximab": "IFX-IV-CD-fistula"},
    ("UC", "adult"): {"Infliximab": "IFX-IV-UC-adult", "Adalimumab": "ADA-UC", "Golimumab": "GOL-UC", "Vedolizumab": "VEDO-IV-UC", "Ustekinumab": "UST-UC",
                      "Tofacitinib": "TOF-UC", "Filgotinib": "FIL-UC", "Upadacitinib": "UPA-UC", "Ozanimod": "OZA-UC"},
    ("UC", "ped"): {"Infliximab": "IFX-IV-UC-ped"},
    ("GIBD", "adult"): {"Infliximab": "IFX-IV-GIBD", "Adalimumab": "ADA-GIBD"},
}
UC_ONLY = {"Golimumab", "Tofacitinib", "Filgotinib", "Ozanimod"}


def not_covered(drug: str, dis: str, grp: str) -> str:
    if dis == "GIBD":
        return "장형 베체트 급여 기준 없음"
    if dis == "CD" and drug in UC_ONLY:
        return "크론병 급여 기준 없음(궤양성 대장염만)"
    if grp == "fistula":
        return "누공성 크론병 해당 없음"
    if grp == "ped":
        return "소아 해당 없음"
    return "해당 기준 없음"


def load_keys():
    keys = defaultdict(dict)
    for l in (OUT / "a_items.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            it = json.loads(l)
            g = it["gate"] + (("-" + it["id"].split("-")[-1]) if it["gate"] == "G6" else "")
            keys[it["drug_id"]][g] = it["answer"]["채점"]
    return keys


# ---------------------------------------------------------------- 판정 엔진

CONV = {"steroid": "코르티코스테로이드제", "immuno": "면역억제제", "een": "완전장관영양법", "5asa": "5-ASA/sulfasalazine",
        "antibiotic": "항생제", "drainage": "배출법"}


def judge(k: dict, p: dict) -> list[str]:
    """이 행의 기준으로 환자를 판정. 실패 사유 목록(비면 인정)."""
    why = []
    g2 = k.get("G2") or {}
    if g2.get("min") and p["age"] < g2["min"]:
        why.append(f"만 {g2['min']}세 이상 필요")
    if g2.get("max") and p["age"] > g2["max"]:
        why.append(f"{g2['max']}세 이하만")
    g3 = k["G3"]
    s = g3.get("척도")
    if s in ("CDAI", "PCDAI"):
        if p.get(s) is None or p[s] < g3["값"]:
            why.append(f"{s} {g3['값']:g} 이상 필요")
    elif s == "PUCAI":
        if p.get("PUCAI") is None or p["PUCAI"] <= g3["값"]:
            why.append(f"PUCAI {g3['값']:g} 초과 필요")
    elif s == "Mayo+Endo":
        lo, hi = g3["Mayo"]
        if p.get("Mayo") is None or not (lo <= p["Mayo"] <= hi) or p.get("Endo", 0) < g3["내시경"]:
            why.append(f"Mayo {lo:g}~{hi:g} 그리고 내시경 subscore {g3['내시경']:g} 이상 필요")
    # 이전 치료
    g4 = k["G4"]
    allowed = set(g4["치료"])
    clause = g4.get("반응 조항", "")
    failed = []
    for t, how in p["prior"].items():
        name = CONV[t]
        hit = name in allowed or (t == "immuno" and any(x in allowed for x in ("6-Mercaptopurine", "Azathioprine", "면역억제 치료")))
        hit = hit or (t == "steroid" and "Corticosteroid" in allowed)
        ok_how = how == "반응 없음" or (how == "부작용" and ("불내성" in clause or "부작용" in clause))
        if hit and ok_how:
            failed.append(t)
    need = g4.get("최소 가지 수") or 1
    if len(failed) < need:
        why.append(f"보편적 치료 {need}가지 이상 실패 필요" if need > 1 else "보편적 치료(스테로이드·면역억제제 등) 실패 필요")
    # 고령·고위험 (JAK)
    if k.get("G5", {}).get("조항") is True and (p["age"] >= 65 or p.get("cv") or p.get("malig")) and not p.get("bio_fail"):
        who = "65세 이상" if p["age"] >= 65 else ("심혈관계 고위험" if p.get("cv") else "악성 종양 위험")
        why.append(f"{who}: 기존 생물학제제 실패·불내성 후에만")
    # 금기: 최근 6개월 이내 심혈관 사건 (Ozanimod, CSV contra_recent_cv_event)
    if k.get("_recent_cv_contra") and p.get("recent_mi"):
        why.append("최근 6개월 이내 심근경색은 투여 금기")
    # 검사 하한
    for lab, col in (("hb", "Hb"), ("anc", "ANC"), ("alc", "ALC")):
        kk = k.get("G6-" + lab)
        if kk and p.get(col) is not None and p[col] < kk["값"]:
            why.append(f"{col} {kk['값']:g} {kk['단위']} 이상 필요")
    return why


def candidates(p: dict) -> list[str]:
    return [d for d in DRUGS if d != p.get("failed_drug")]


def solve(keys, p: dict) -> dict:
    keys["OZA-UC"]["_recent_cv_contra"] = True
    grp = "fistula" if p.get("fistula") else ("ped" if p["age"] <= 18 and p["dis"] != "GIBD" else "adult")
    rows = ROW[(p["dis"], grp)]
    res = {}
    for d in candidates(p):
        if d not in rows:
            res[d] = ["제외", not_covered(d, p["dis"], grp)]
            continue
        why = judge(keys[rows[d]], p)
        note = " (정맥주사만)" if (p["dis"], grp) == ("UC", "ped") and d == "Infliximab" else ""
        res[d] = ["인정" + note] if not why else ["제외", "; ".join(why)]
    return res


# ---------------------------------------------------------------- 환자 설명


def describe(p: dict) -> str:
    sex = p.get("sex", "남성")
    dis = {"CD": "크론병", "UC": "궤양성 대장염", "GIBD": "장형 베체트"}[p["dis"]]
    parts = [f"{p['age']}세 {sex}"]
    if p["dis"] == "GIBD":
        parts.append("베체트병으로 진단되었고 대장내시경에서 장 궤양이 확인된 장형 베체트")
    elif p.get("fistula"):
        parts.append("배농되는 항문주위 누공이 있는 누공성 크론병(장관 염증은 CDAI 150으로 활동성 낮음)")
    else:
        parts.append(f"활동성 {dis}")
    for s in ("CDAI", "PCDAI", "PUCAI"):
        if p.get(s) is not None:
            parts.append(f"{s} {p[s]}")
    if p.get("Mayo") is not None:
        parts.append(f"Mayo score {p['Mayo']}, 내시경 subscore {p['Endo']}")
    ko = {"steroid": "코르티코스테로이드", "immuno": "아자티오프린", "een": "완전장관영양법", "5asa": "메살라진(5-ASA)", "antibiotic": "항생제", "drainage": "배농술(배출법)"}
    nores = [ko[t] for t, h in p["prior"].items() if h == "반응 없음"]
    side = [ko[t] for t, h in p["prior"].items() if h == "부작용"]
    if nores:
        parts.append("·".join(nores) + "에 반응이 없었다")
    if side:
        parts.append("·".join(side) + "은(는) 부작용으로 중단했다")
    parts.append(p.get("bio_text", "TNF 억제제 등 생물학제제는 사용한 적이 없다"))
    if p.get("recent_mi"):
        parts.append("4개월 전 심근경색으로 입원했다(심혈관계 고위험군)")
    elif p.get("cv"):
        parts.append("심혈관계 고위험군(5년 전 심근경색 병력)")
    if p.get("malig"):
        parts.append("악성 종양 위험군(3년 전 대장암 수술)")
    if any(p.get(x) is not None for x in ("Hb", "ANC", "ALC")):
        parts.append(f"혈액검사 Hb {p.get('Hb', 12):g} g/dL, ANC {p.get('ANC', 3000):,} cells/mm³, ALC {p.get('ALC', 1500):,} cells/mm³")
    return ", ".join(parts)


# ---------------------------------------------------------------- 시나리오 (조건을 하나씩·둘씩 바꿔 정답 집합이 겹치지 않게)

LAB = {"Hb": 12, "ANC": 3000, "ALC": 1500}
CD2 = {"steroid": "반응 없음", "immuno": "반응 없음"}
UC2 = {"steroid": "반응 없음", "immuno": "반응 없음"}
TNF_FAIL = "아달리무맙(TNF 억제제)에 적절한 반응이 없었다"
TF = dict(bio_fail=True, bio_text=TNF_FAIL, failed_drug="Adalimumab")
S = [
    # 성인 크론병
    ("cd-base", "기본(모든 조건 충족)", dict(dis="CD", age=45, CDAI=260, prior=CD2, **LAB)),
    ("cd-cdai219", "활성도 경계 미달", dict(dis="CD", age=45, CDAI=219, prior=CD2, **LAB)),
    ("cd-prior1", "이전 치료 1가지", dict(dis="CD", age=45, CDAI=260, prior={"steroid": "반응 없음"}, **LAB)),
    ("cd-intol", "부작용 중단 경로", dict(dis="CD", age=45, CDAI=260, prior={"steroid": "반응 없음", "immuno": "부작용"}, **LAB)),
    ("cd-68", "65세 이상", dict(dis="CD", age=68, CDAI=260, prior=CD2, sex="여성", **LAB)),
    ("cd-68-tnf", "65세 이상 + TNF 실패", dict(dis="CD", age=68, CDAI=260, prior=CD2, **TF, sex="여성", **LAB)),
    ("cd-cv", "심혈관 고위험", dict(dis="CD", age=52, CDAI=260, prior=CD2, cv=True, **LAB)),
    ("cd-malig-tnf", "악성종양 위험 + TNF 실패", dict(dis="CD", age=52, CDAI=260, prior=CD2, malig=True, **TF, **LAB)),
    ("cd-hb75", "Hb 7.5", dict(dis="CD", age=45, CDAI=260, prior=CD2, **{**LAB, "Hb": 7.5})),
    ("cd-anc900", "ANC 900", dict(dis="CD", age=45, CDAI=260, prior=CD2, **{**LAB, "ANC": 900})),
    ("cd-hb85", "Hb 8.5", dict(dis="CD", age=45, CDAI=260, prior=CD2, **{**LAB, "Hb": 8.5})),
    ("cd-68-tnf-hb75", "65세 이상 + TNF 실패 + Hb 7.5", dict(dis="CD", age=70, CDAI=260, prior=CD2, **TF, sex="여성", **{**LAB, "Hb": 7.5})),
    # 성인 궤양성 대장염
    ("uc-base", "기본(모든 조건 충족)", dict(dis="UC", age=45, Mayo=8, Endo=2, prior=UC2, sex="여성", **LAB)),
    ("uc-mayo5", "Mayo 경계 미달", dict(dis="UC", age=45, Mayo=5, Endo=2, prior=UC2, sex="여성", **LAB)),
    ("uc-endo1", "내시경 subscore 미달", dict(dis="UC", age=45, Mayo=9, Endo=1, prior=UC2, sex="여성", **LAB)),
    ("uc-5asa", "보편적 치료 미사용(5-ASA만)", dict(dis="UC", age=45, Mayo=8, Endo=2, prior={"5asa": "반응 없음"}, sex="여성", **LAB)),
    ("uc-intol", "부작용 중단 경로", dict(dis="UC", age=45, Mayo=8, Endo=2, prior={"steroid": "반응 없음", "immuno": "부작용"}, sex="여성", **LAB)),
    ("uc-68", "65세 이상", dict(dis="UC", age=68, Mayo=8, Endo=2, prior=UC2, sex="여성", **LAB)),
    ("uc-68-tnf", "65세 이상 + TNF 실패", dict(dis="UC", age=68, Mayo=8, Endo=2, prior=UC2, **TF, sex="여성", **LAB)),
    ("uc-cv", "심혈관 고위험", dict(dis="UC", age=55, Mayo=8, Endo=2, prior=UC2, cv=True, **LAB)),
    ("uc-recent-mi", "최근 심근경색(4개월 전)", dict(dis="UC", age=58, Mayo=8, Endo=2, prior=UC2, cv=True, recent_mi=True, **LAB)),
    ("uc-hb85", "Hb 8.5", dict(dis="UC", age=45, Mayo=8, Endo=2, prior=UC2, **{**LAB, "Hb": 8.5})),
    ("uc-hb75", "Hb 7.5", dict(dis="UC", age=45, Mayo=8, Endo=2, prior=UC2, **{**LAB, "Hb": 7.5})),
    ("uc-anc900", "ANC 900", dict(dis="UC", age=45, Mayo=8, Endo=2, prior=UC2, **{**LAB, "ANC": 900})),
    ("uc-alc450", "ALC 450", dict(dis="UC", age=45, Mayo=8, Endo=2, prior=UC2, **{**LAB, "ALC": 450})),
    ("uc-68-hb85", "65세 이상 + Hb 8.5", dict(dis="UC", age=68, Mayo=8, Endo=2, prior=UC2, sex="여성", **{**LAB, "Hb": 8.5})),
    ("uc-tnf-hb85", "TNF 실패 + Hb 8.5", dict(dis="UC", age=45, Mayo=8, Endo=2, prior=UC2, **TF, **{**LAB, "Hb": 8.5})),
    # 소아
    ("pcd-base", "소아 크론병 기본", dict(dis="CD", age=13, PCDAI=35, prior=CD2)),
    ("pcd-29", "소아 크론병 PCDAI 미달", dict(dis="CD", age=13, PCDAI=29, prior=CD2)),
    ("puc-base", "소아 궤양성 대장염 기본", dict(dis="UC", age=13, PUCAI=50, prior=UC2, sex="여성")),
    ("puc-45", "소아 궤양성 대장염 PUCAI 45", dict(dis="UC", age=13, PUCAI=45, prior=UC2, sex="여성")),
    # 누공성 크론병
    ("fcd-base", "누공성 크론병 기본", dict(dis="CD", age=40, fistula=True, prior={"antibiotic": "반응 없음", "drainage": "반응 없음"})),
    ("fcd-abx", "누공성 크론병 항생제만", dict(dis="CD", age=40, fistula=True, prior={"antibiotic": "반응 없음"})),
    # 장형 베체트
    ("bd-base", "장형 베체트 기본", dict(dis="GIBD", age=45, prior={"steroid": "반응 없음", "5asa": "반응 없음"}, sex="여성")),
    ("bd-18", "장형 베체트 18세", dict(dis="GIBD", age=18, prior={"steroid": "반응 없음", "5asa": "반응 없음"}, sex="여성")),
    ("bd-prior1", "장형 베체트 이전 치료 1가지", dict(dis="GIBD", age=45, prior={"steroid": "반응 없음"}, sex="여성")),
    ("bd-intol", "장형 베체트 부작용 중단 경로", dict(dis="GIBD", age=45, prior={"5asa": "반응 없음", "immuno": "부작용"}, sex="여성")),
]

TRAP = {
    "uc-68": "고령 조건은 JAK 3종에만 적용 (Ozanimod·생물학제제는 인정)",
    "uc-hb85": "같은 Hb 8.5에서 Tofacitinib(하한 9)만 제외",
    "cd-hb85": "Hb 8.5에서 Upadacitinib(하한 8)은 인정 (궤양성 대장염 Tofacitinib과 대비)",
    "uc-recent-mi": "JAK 3종은 심혈관 고위험으로, Ozanimod는 최근 6개월 이내 심근경색 금기로 제외",
    "bd-18": "같은 질환에서 Infliximab은 만 19세 이상, Adalimumab은 연령 조건 없음",
    "fcd-base": "누공성 크론병은 Infliximab만 해당",
    "cd-base": "기준 혼동: TNF 실패를 요구하면 Vedolizumab·Ustekinumab·Upadacitinib을 잘못 제외",
    "uc-base": "기준 혼동: TNF 실패를 요구하면 비-TNF 약을 잘못 제외",
    "cd-cdai219": "인정되는 약 없음",
    "pcd-base": "소아 크론병은 Infliximab·Adalimumab만",
    "puc-base": "소아 궤양성 대장염은 Infliximab(정맥주사)만",
}


def main() -> int:
    keys = load_keys()
    items, sigs = [], Counter()
    for sid, label, p in S:
        res = solve(keys, p)
        ok = [d + (res[d][0][2:] if len(res[d][0]) > 2 else "") for d in candidates(p) if res[d][0].startswith("인정")]
        ng = {d: res[d][1] for d in candidates(p) if res[d][0] == "제외"}
        sigs[(tuple(ok), tuple(sorted(ng.items())))] += 1
        q = (f"{describe(p)}. 다음 약 중 이 환자에게 급여가 인정되는 약과 제외되는 약을 모두 쓰고, 제외되는 약은 이유를 쓰시오: "
             + ", ".join(candidates(p)) + ". (형식: '인정: …' / '제외: 약 - 이유')")
        items.append({"id": f"D-{sid}", "type": "D", "gate": "약제 선택", "기준": label, "drug_id": "MULTI", "drug_class": "",
                      "drug_name": "후보 9종", "question": q,
                      "answer": {"정답": {"인정": ok, "제외": ng}, "채점": {"인정": ok, "제외": list(ng), "제외 이유": ng, "함정": TRAP.get(sid, "")},
                                 "형식": "약제 집합"},
                      "원문": "A형 채점 열쇠(약·적응증 행별) + 가이드북 '해당 없음' 표기(p.23·24·26·27)로 코드가 판정",
                      "source_page": "p.21~27; 고시문 p.35~57", "짝키": f"D|{sid}", "patient": p})
    dup = [s for s, n in sigs.items() if n > 1]
    (OUT / "d_items.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    lines = ["| # | 사례 | 환자 | 인정 | 제외 (이유) |", "| --- | --- | --- | --- | --- |"]
    for n, it in enumerate(items, 1):
        a = it["answer"]["정답"]
        ex = "; ".join(f"{d}: {w}" for d, w in a["제외"].items())
        lines.append(f"| {n} | {it['기준']} | {describe(it['patient'])} | {', '.join(a['인정']) or '없음'} | {ex} |")
    (OUT / "d_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summ = {"문항": len(items), "인정 약 수 분포": dict(Counter(len(i["answer"]["정답"]["인정"]) for i in items)),
            "정답 집합이 같은 사례": len(dup), "함정 표시": sum(1 for i in items if i["answer"]["채점"]["함정"]),
            "만든 날": "2026-11-11", "API": "사용 안 함"}
    (OUT / "d_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
