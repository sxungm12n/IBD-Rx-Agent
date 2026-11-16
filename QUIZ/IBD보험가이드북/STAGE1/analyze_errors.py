"""에이전트 오답 원인 분류 1차 (API 없음).
각 문항의 '핵심 쪽'을 에이전트가 검색해 왔는지(top-5 sources)를 기준으로 나눈다.
결과: STAGE1/eval_out/error_taxonomy_agent.json (+ 콘솔 요약)
"""
import json, re, collections
from pathlib import Path

S1 = Path("/Users/limseongmin/IBD Rx Agent/QUIZ/IBD보험가이드북/STAGE1")
OUT, EV = S1 / "output", S1 / "eval_out"

def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

def pages(sp):
    """'p.20; p.23; p.35' / 'p.21~27' → 정수 쪽 목록"""
    out = []
    for a, b in re.findall(r"(\d+)(?:~(\d+))?", sp or ""):
        out += list(range(int(a), int(b or a) + 1))
    return out

CRIT_GATES = {"G3", "G4", "E", "G5", "전체", "W"}           # 급여 기준(고시문) 쪽이 핵심
CRIT_C = {"전체", "활성도", "이전 치료", "유지 기준", "나이", "고령·고위험", "검사 하한"}

def key_pages(it):
    sp = [p for p in pages(it.get("source_page")) if p != 34]
    crit = [p for p in sp if p >= 35]
    g = it["gate"]
    if it["type"] == "C" or g in CRIT_GATES or g == "G6" or it["기준"].startswith("금기(체크"):
        return crit or sp
    return sp                                                    # 나이·용량·처방기간 등: 목록 중 아무 쪽

# D: 성분 + 질환 → 고시문 쪽
DPAGE = {("Infliximab", "CD"): [35, 38], ("Infliximab", "UC"): [36, 39], ("Infliximab", "GIBD"): [37],
         ("Adalimumab", "CD"): [40], ("Adalimumab", "UC"): [41], ("Adalimumab", "GIBD"): [42],
         ("Golimumab", "UC"): [43], ("Vedolizumab", "CD"): [44], ("Vedolizumab", "UC"): [45],
         ("Ustekinumab", "CD"): [46], ("Ustekinumab", "UC"): [47], ("Filgotinib", "UC"): [48, 49],
         ("Upadacitinib", "CD"): [50, 52], ("Upadacitinib", "UC"): [51, 52],
         ("Tofacitinib", "UC"): [54, 55], ("Ozanimod", "UC"): [56, 57]}

def retrieved(ans):
    return [s["page"] for s in ans.get("응답", {}).get("sources", [])]

rows, stats = [], collections.defaultdict(lambda: collections.Counter())
SETS = [("A", "a_items", "agent_gpt-5.6-terra", "graded_v21.jsonl"),
        ("A2", "a2_items", "a2_agent_gpt-5.6-terra", "graded_v21.jsonl"),
        ("C", "c_items", "c_agent_gpt-5.6-terra", "graded_code.jsonl"),
        ("D", "d_items", "d_agent_gpt-5.6-terra", "graded_code.jsonl")]
for T, itf, d, gf in SETS:
    items = {i["id"]: i for i in jl(OUT / f"{itf}.jsonl")}
    ans = {a["id"]: a for a in jl(EV / d / "answers.jsonl")}
    gr = {g["id"]: g for g in jl(EV / d / gf)}
    for iid, it in items.items():
        a, g = ans[iid], gr[iid]
        ret = retrieved(a)
        verdict = g["최종"]
        if T == "D":
            dis = it["patient"]["dis"]
            need = sorted(set(it["answer"]["채점"]["인정"]) | set(g.get("가이드북 약 중 틀리게 넣음", [])))
            miss_drugs = g.get("빠뜨림", [])
            wrong_in = g.get("가이드북 약 중 틀리게 넣음", [])
            per = {dr: any(p in ret for p in DPAGE.get((dr, dis), [])) for dr in need}
            hit_any = all(per.get(dr, False) for dr in miss_drugs + wrong_in) if (miss_drugs or wrong_in) else True
            kp = {dr: DPAGE.get((dr, dis), []) for dr in need}
            extra = {"질환": dis, "빠뜨림": miss_drugs, "틀리게 넣음": wrong_in,
                     "실패약 재사용": g.get("이미 실패한 약 다시 씀"), "해외약": g.get("해외·가이드북 밖 약"),
                     "약별 쪽 검색": per, "정답 약 쪽 검색 비율": round(sum(per[x] for x in it["answer"]["채점"]["인정"]) / max(1, len(it["answer"]["채점"]["인정"])), 2) if it["answer"]["채점"]["인정"] else None}
        else:
            kp = key_pages(it)
            hit_any = any(p in ret for p in kp)
            extra = {}
        main = not (T == "A" and it["기준"].startswith("금기"))
        stats[T]["n"] += 1
        stats[T][f"{verdict}"] += 1
        stats[T][f"{verdict}|hit" if hit_any else f"{verdict}|miss"] += 1
        if verdict != "맞음":
            rows.append({"id": iid, "유형": T, "본문항": main, "gate": it["gate"], "기준": it["기준"],
                         "질문": it["question"], "정답": it["answer"]["정답"], "에이전트 답": g["채점 대상"],
                         "판정": verdict, "핵심 쪽": kp, "검색된 쪽": ret, "핵심 쪽 검색": hit_any,
                         "판정 이유": (g.get("LLM") or {}).get("이유", ""), **extra})

(EV / "error_taxonomy_agent.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("유형 | 문항 | 맞음(핵심쪽 검색O/X) | 부분(O/X) | 틀림(O/X)")
for T in ["A", "A2", "C", "D"]:
    s = stats[T]
    f = lambda v: f"{s[v]} ({s[v+'|hit']}/{s[v+'|miss']})"
    print(T, s["n"], f("맞음"), f("부분"), f("틀림"))
print("오답·부분 저장:", len(rows))
