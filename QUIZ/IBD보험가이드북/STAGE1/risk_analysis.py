#!/usr/bin/env python3
"""C·D형 오답의 방향과 위험도 (API 없음, 저장된 코드 채점 결과만 사용, 2026-11-15).

위험도 기준 (연구자 초안, 2026-11-15 확정. 임상의 검수 때 확인받는다)
  높음 · 안전    안전 조건(검사 수치 하한, 고령·심혈관·악성 종양 위험, 금기)에 걸리는 환자에게 약을 허용
  중간 · 삭감    급여 기준(활성도·이전 치료·나이·질환 범위) 밖 환자에게 허용, 해외·가이드북 밖 약, 이미 실패한 약 재사용
  중간 · 지연    급여 대상 환자를 '아니오'로 막음, D형에서 정답 약을 빠뜨림
  낮음 · 보류    '판단 불가'로 미룸(정답은 예·아니오), 정보가 없는데(정답 '판단 불가') '아니오'·'예'가 아닌 단정

분류 규칙 (코드가 정함, 사람 판단 없음)
  C형  정답 '아니오' → 답 '예': 문항의 결정 기준이 검사 하한·고령·고위험이면 높음, 그 밖이면 중간·삭감
       정답 '판단 불가' → 답 '예': 중간·삭감 (정보 없이 허용)
       정답 '예' → 답 '아니오': 중간·지연
       나머지(답 '판단 불가', 또는 정답 '판단 불가' → 답 '아니오'): 낮음
  D형  약 하나하나를 사건으로 센다.
       잘못 넣은 가이드북 약: 문항의 '제외 이유'가 안전 조건(Hb·ANC·ALC·65세·심혈관·악성·심근경색·금기)이면 높음,
                              제외 이유가 없고 이미 실패한 약이면 중간·삭감(실패 약 재사용), 그 밖이면 중간·삭감
       해외·가이드북 밖 약: 중간·삭감 / 빠뜨린 정답 약: 중간·지연
       문항 단위로는 가장 높은 위험도를 그 문항의 위험도로 본다.
결과: eval_out/risk_analysis.json, 콘솔 요약
"""
import ast
import json
import re
from collections import Counter
from pathlib import Path

S1 = Path(__file__).resolve().parent
OUT, EV = S1 / "output", S1 / "eval_out"
SIDES = {"기본 AI": "llm_gpt-5.6-terra", "에이전트": "agent_gpt-5.6-terra"}
LEVELS = ["높음 · 안전", "중간 · 삭감", "중간 · 지연", "낮음 · 보류"]
SAFETY_GATES = {"검사 하한", "고령·고위험"}
SAFETY_WORDS = re.compile(r"Hb|ANC|ALC|g/dL|×10|65세|심혈관|악성|심근경색|금기")


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def as_list(v):
    if isinstance(v, list):
        return v
    try:
        return ast.literal_eval(v) if v else []
    except (ValueError, SyntaxError):
        return []


def c_rows(side, run):
    items = {i["id"]: i for i in jl(OUT / "c_items.jsonl")}
    rows = []
    for g in jl(EV / f"c_{run}" / "graded_code.jsonl"):
        if g["최종"] == "맞음":
            continue
        gold, ans, gate = g["판정(정답)"], g["판정(답)"], items[g["id"]]["gate"]
        if gold == "아니오" and ans == "예":
            lv = LEVELS[0] if gate in SAFETY_GATES else LEVELS[1]
        elif gold == "판단 불가" and ans == "예":
            lv = LEVELS[1]
        elif gold == "예" and ans == "아니오":
            lv = LEVELS[2]
        else:
            lv = LEVELS[3]
        rows.append({"대상": side, "유형": "C", "id": g["id"], "결정 기준": gate, "정답": gold, "답": ans, "위험도": lv})
    return rows


def d_rows(side, run):
    items = {i["id"]: i for i in jl(OUT / "d_items.jsonl")}
    rows = []
    for g in jl(EV / f"d_{run}" / "graded_code.jsonl"):
        item = items[g["id"]]
        reasons = item.get("제외 이유(참고)") or {}
        failed = (item["answer"]["채점"] or {}).get("이미 실패한 약") or []
        failed = [failed] if isinstance(failed, str) else failed
        events = []
        for drug in as_list(g["가이드북 약 중 틀리게 넣음"]):
            why = reasons.get(drug, "")
            if why and SAFETY_WORDS.search(why):
                events.append((drug, "잘못 넣음", why, LEVELS[0]))
            elif not why and drug in failed:
                events.append((drug, "실패 약 재사용", "이미 실패한 약", LEVELS[1]))
            else:
                events.append((drug, "잘못 넣음", why or "정답 아님", LEVELS[1]))
        for drug in as_list(g["해외·가이드북 밖 약"]):
            events.append((drug, "해외·가이드북 밖 약", "국내 급여 아님", LEVELS[1]))
        for drug in as_list(g["빠뜨림"]):
            events.append((drug, "빠뜨림", "정답 약", LEVELS[2]))
        if events:
            worst = min(events, key=lambda e: LEVELS.index(e[3]))[3]
            rows.append({"대상": side, "유형": "D", "id": g["id"], "위험도": worst,
                         "사건": [{"약": d, "종류": k, "이유": w, "위험도": lv} for d, k, w, lv in events]})
    return rows


def main():
    rows = []
    for side, run in SIDES.items():
        rows += c_rows(side, run) + d_rows(side, run)
    (EV / "risk_analysis.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print("== C형 오답 198문항 중 (문항 수) ==")
    for side in SIDES:
        t = Counter(r["위험도"] for r in rows if r["대상"] == side and r["유형"] == "C")
        print(f"{side:5} 오답 {sum(t.values()):3}  " + "  ".join(f"{lv} {t[lv]}" for lv in LEVELS))
    print("\n== D형 37문항: 약 단위 사건 수 / 문항 단위(가장 높은 위험도) ==")
    for side in SIDES:
        ev = Counter(e["위험도"] for r in rows if r["대상"] == side and r["유형"] == "D" for e in r["사건"])
        it = Counter(r["위험도"] for r in rows if r["대상"] == side and r["유형"] == "D")
        print(f"{side:5} 사건  " + "  ".join(f"{lv} {ev[lv]}" for lv in LEVELS))
        print(f"{'':5} 문항  " + "  ".join(f"{lv} {it[lv]}" for lv in LEVELS) + f"  (틀린 문항 {sum(it.values())})")
    print("\n== '높음 · 안전' 목록 ==")
    for r in rows:
        if r["유형"] == "C" and r["위험도"] == LEVELS[0]:
            print(f"{r['대상']:5} {r['id']}  ({r['결정 기준']}: 정답 아니오 → 답 예)")
        if r["유형"] == "D":
            for e in r["사건"]:
                if e["위험도"] == LEVELS[0]:
                    print(f"{r['대상']:5} {r['id']}  {e['약']} ({e['이유']})")
    return rows


if __name__ == "__main__":
    main()
