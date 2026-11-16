#!/usr/bin/env python3
"""STAGE1 — C형: 환자 사례 판정 문항 (2026-11-11).

"이 환자에게 이 약의 급여가 인정되는가?" → 예 / 아니오 / 판단 불가
- 정답은 코드가 A형 채점 열쇠(= 가이드북 CSV에서 뽑은 기준)로 판정한다. LLM 미사용, OpenAI API 호출 없음.
- 사례는 '모든 조건을 만족하는 기본 환자'에서 조건 하나만 바꿔 만든다 → 어느 기준을 모르는지 알 수 있다.
- 경계값을 쓴다 (예: CDAI 220 인정 / 219 불인정).
- 함정: 비-TNF 약의 기본 사례는 'TNF 억제제 사용 이력 없음'을 명시 → TNF 실패를 요구하면 틀림(기준 혼동).
       같은 Hb 8.5에서 Tofacitinib(하한 9)은 불인정, Filgotinib·Upadacitinib(하한 8)은 인정.
       고령 조항이 없는 약(대조)은 68세여도 인정.
사용: python3 STAGE1/make_c.py  → output/c_items.jsonl, output/c_summary.json
"""
from __future__ import annotations

import csv
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE.parents[2] / "data" / "IBD보험가이드북.csv"
OUT = HERE / "output"

# 시작 판정 질문: 고시 급여 기준과 가이드북의 투여 전 확인사항(체크리스트: 검사 하한·금기)을 함께 적용하게 한다
ASK_START = ("가이드북의 급여 기준으로 판단할 때(사례에 검사 수치·병력이 있으면 투여 전 확인사항도 적용), 이 환자는 이 약의 급여 대상인가? "
             "(예 / 아니오 / 판단 불가 중 하나와 이유)")
# 사례에 적지 않은 체크리스트 항목(결핵·감염·임신 등)을 '정보 없음'으로 읽지 않게 한다
OTHER_CHECKS = "사례에 적히지 않은 투여 전 확인사항(결핵·감염·임신 등)은 모두 문제없는 것으로 본다."
# 피하주사 제형(램시마 SC·킨텔레스 SC)은 IV 2회 유도 후 SC로 이어 가는 용법이라, 시작 판정에서 'IV를 안 맞았으니 SC 불가'로 읽히지 않게 계획을 적는다 (결정 20, 2026-11-13)
SC_PLAN = "정맥주사(IV) 2회로 유도한 뒤 이 피하주사(SC)로 유지할 계획이다."
DIS = {"CD": "크론병", "UC": "궤양성 대장염", "GIBD": "장형 베체트"}
TNF = {"Infliximab", "Adalimumab", "Golimumab"}


def load():
    items = [json.loads(l) for l in (OUT / "a_items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    keys, names = defaultdict(dict), {}
    for it in items:
        g = it["gate"] + (("-" + it["id"].split("-")[-1]) if it["gate"] == "G6" else "")
        keys[it["drug_id"]][g] = it["answer"]["채점"]
        names[it["drug_id"]] = it["drug_name"]
    raw = CSV_PATH.read_bytes().decode("utf-8-sig")
    rows = {r["drug_id"].strip(): {k.strip(): (v or "") for k, v in r.items()} for r in csv.DictReader(io.StringIO(raw))}
    return keys, names, rows


# ---------------------------------------------------------------- 문장 조각


def activity(k3: dict, mode: str) -> tuple[str, str] | None:
    """mode: pass(경계값 충족) / fail(경계값 바로 아래) / missing. (문장, 이유)"""
    s = k3.get("척도")
    if s is None:
        return None
    if mode == "missing":
        return "질병 활성도 점수는 이 사례에 제시되지 않았다", "활성도 점수가 제시되지 않아 급여 기준 충족 여부를 판단할 수 없음"
    if s in ("CDAI", "PCDAI"):
        v = int(k3["값"])
        return (f"{s} {v}", f"{s} {v} ≥ {v}") if mode == "pass" else (f"{s} {v - 1}", f"{s} {v - 1} < {v}")
    if s == "PUCAI":  # 초과
        v = int(k3["값"])
        return (f"PUCAI {v + 5}", f"PUCAI {v + 5} > {v}") if mode == "pass" else (f"PUCAI {v}", f"PUCAI {v}는 {v} 초과가 아님")
    if s == "Mayo+Endo":
        lo, endo = int(k3["Mayo"][0]), int(k3["내시경"])
        if mode == "pass":
            return f"Mayo score {lo}, 내시경 subscore {endo}", f"Mayo {lo}(6~12) 그리고 내시경 {endo} ≥ {endo}"
        return f"Mayo score {lo - 1}, 내시경 subscore {endo}", f"Mayo {lo - 1} < {lo}"
    raise ValueError(s)


def prior(k4: dict, mode: str, disease: str, ped: bool) -> tuple[str, str]:
    """mode: pass / one(1가지만) / intolerance(불내성 경로) / none(해당 약 미사용)."""
    tx = k4["치료"]
    two = k4.get("최소 가지 수") == 2
    if "항생제" in tx:  # 누공성
        if mode == "one":
            return "항생제 치료만 받았고 반응이 없었다", "보편적 치료 2가지 이상(항생제·배출법·면역억제 치료 등)이 필요"
        return "항생제 치료와 배농술(배출법)에 반응이 없었다", "보편적 치료 2가지 이상에 반응 없음"
    if "5-ASA/sulfasalazine" in tx:  # 베체트
        if mode == "one":
            return "코르티코스테로이드만 사용했고 반응이 없었다", "보편적 치료 2가지 이상 필요"
        if mode == "intolerance":
            return "메살라진(5-ASA)에 반응이 없었고 아자티오프린은 부작용으로 중단했다", "반응 없음·부작용 중단도 인정"
        return "코르티코스테로이드와 메살라진(5-ASA)에 반응이 없었다", "보편적 치료 2가지 이상에 반응 없음"
    if ped and "완전장관영양법" in tx:
        if mode == "one":
            return "완전장관영양법만 시행했고 반응이 없었다", "적어도 2가지 이상 필요"
        if mode == "intolerance":
            return "완전장관영양법에 반응이 없었고 아자티오프린은 부작용(백혈구 감소)으로 중단했다", "반응 없음·내약성 없음도 인정"
        return "코르티코스테로이드와 완전장관영양법에 반응이 없었다", "보편적 치료 2가지 이상에 반응 없음"
    if two:
        if mode == "one":
            return "코르티코스테로이드만 사용했고 반응이 없었다", "보편적 치료 2가지 이상 필요"
        if mode == "intolerance":
            return "코르티코스테로이드에 반응이 없었고 아자티오프린은 부작용(백혈구 감소)으로 중단했다", "반응 없음·내약성 없음도 인정"
        return "코르티코스테로이드와 아자티오프린에 반응이 없었다", "보편적 치료 2가지 이상에 반응 없음"
    # 궤양성 대장염: Corticosteroid / 6-MP / Azathioprine 등
    if mode == "one":  # UC는 최소 가지 수가 없으므로 '보편적 치료 미사용'으로 깬다
        return "메살라진(5-ASA)만 사용했고 코르티코스테로이드·면역억제제는 사용한 적이 없다", "코르티코스테로이드·6-MP·아자티오프린 등 보편적 치료 실패가 필요"
    if mode == "intolerance":
        return "코르티코스테로이드에 적정한 반응이 없었고 아자티오프린은 부작용으로 중단했다", "반응 없음·내약성 없음도 인정"
    return "코르티코스테로이드와 아자티오프린에 적정한 반응이 없었다", "보편적 치료에 반응 없음"


def maintenance(kE: dict, ok: bool) -> tuple[str, str] | None:
    k, t = kE["종류"], kE.get("시점", "평가 시점")
    if k == "CDAI":  # 70점 또는 25% — 인정 사례는 '25% 경로'로 (또는 이해 확인)
        b, a = (240, 175) if ok else (300, 250)
        d, p = b - a, round((b - a) / b * 100, 1)
        why = f"{d}점({p}%) 감소 → " + ("25% 이상이므로 인정('또는')" if ok else "70점 미만이고 25% 미만")
        return f"투여 전 CDAI {b}, {t} 평가 CDAI {a}", why
    if k == "PCDAI":
        b, a = (40, 30) if ok else (40, 35)
        return f"투여 전 PCDAI {b}, {t} 평가 PCDAI {a}", f"{b - a}점({(b - a) / b * 100:.1f}%) 감소 → " + ("25% 이상이므로 인정" if ok else "12.5점 미만이고 25% 미만")
    if k == "PUCAI":
        # '기준보다 20점 이상 감소'의 '기준'을 투여 전 점수로 읽든 진입 기준(45 초과)으로 읽든 같은 답이 나오는 값
        b, a = (65, 25) if ok else (60, 45)
        return f"투여 전 PUCAI {b}, {t} 평가 PUCAI {a}", f"{b - a}점 감소 → " + (
            "20점 이상 (진입 기준 45보다도 20점 낮음)" if ok else "20점 미만 (진입 기준 45보다 20점 낮지도 않음)")
    if k == "Mayo":
        if ok:
            return f"투여 전 Mayo score 10(직장출혈 subscore 2), {t} 평가 Mayo score 6(직장출혈 subscore 1)", "4점(40%) 감소 그리고 직장출혈 1점 감소 → 인정"
        return f"투여 전 Mayo score 10(직장출혈 subscore 2), {t} 평가 Mayo score 8(직장출혈 subscore 1)", "2점(20%) 감소 → 30% 이상·3점 이상 감소 미충족"
    if k == "fistula":
        b, a = (4, 2) if ok else (4, 3)
        return f"투여 전 배농 누공 {b}개, {t} 평가 누공 {a}개", f"누공 {(b - a) / b * 100:.0f}% 감소 → " + ("50% 이상" if ok else "50% 미만")
    if k == "DAIBD":
        b, a = (80, 55) if ok else (80, 70)
        return f"투여 전 DAIBD {b}, {t} 평가 DAIBD {a}", f"{b - a}점 감소 → " + ("20점 이상" if ok else "20점 미만")
    return None


# ---------------------------------------------------------------- 사례 만들기


def make(keys, names, rows) -> list[dict]:
    out = []
    seen_maint_missing: set = set()
    for did, k in keys.items():
        if "G3" not in k or "G4" not in k:
            continue  # 5-ASA·MTX 등 급여 활성도 기준이 없는 행은 제외
        r = rows[did]
        dis = DIS.get(r["disease"], r["disease"])
        ped = r["age_group"] == "pediatric"
        fistula = k["G3"].get("척도") is None and "누공" in json.dumps(k["G3"], ensure_ascii=False)
        gibd = r["disease"] == "GIBD"
        name, en = names[did], r["drug_en"]
        age_min = (k.get("G2") or {}).get("min")
        base_age = 13 if ped else max(45, (age_min or 0) + 10)
        jak = k.get("G5", {}).get("조항") is True
        labs = {g: v for g, v in k.items() if g.startswith("G6-")}
        page = r["source_page"]
        # 소분자제제(JAK·Ozanimod)는 체크리스트에 '임신 가능성이 있는 여성 투여 불가·보류'가 있으므로 남성 사례만 쓴다
        sex = "남성" if (r["drug_class"] == "소분자제제" or len(out) % 2 == 0) else "여성"

        def case(ctype, gate, verdict, why, *, age=None, act="pass", pr="pass", extra=(), lab_over=None, anc=3000, alc=1500, trap="", maint=None):
            a = age if age is not None else base_age
            parts = [f"{a}세 {sex}"]
            if fistula:
                parts.append("누공성 크론병(배농되는 항문주위 누공 4개)")
            elif gibd:
                parts.append("베체트병으로 진단되었고 대장내시경에서 장 궤양이 확인된 장형 베체트")
            else:
                parts.append(("내시경으로 진단된 " if ped and r["disease"] == "UC" else "") + f"활동성 {dis}")  # '중등도-중증'은 쓰지 않는다: 점수로 판단하게 (기준 미달 사례에서 답을 암시하지 않게)
            if maint is None:
                ac = activity(k["G3"], act)
                if ac:
                    parts.append(ac[0])
                parts.append(prior(k["G4"], pr, r["disease"], ped)[0])
                parts += list(extra)
                if labs:
                    hb = lab_over if lab_over is not None else 12.0
                    parts.append(f"혈액검사 Hb {hb:g} g/dL, ANC {anc:,} cells/mm³, ALC {alc:,} cells/mm³")
                plan = (SC_PLAN + " ") if "-SC-" in did else ""
                q = f"[{name}] " + ", ".join(parts) + ". " + plan + OTHER_CHECKS + " " + ASK_START
            else:
                q = f"[{name}] " + ", ".join(parts) + f". 이 약으로 급여 인정을 받아 투여 중이다. {maint}. 유지요법이 계속 인정되는가? (예 / 아니오 / 판단 불가 중 하나와 이유)"
            out.append({
                "id": f"C-{did}-{ctype}", "type": "C", "gate": gate, "기준": "환자 판정", "drug_id": did,
                "drug_class": r["drug_class"], "drug_name": name, "question": q,
                "answer": {"정답": verdict, "채점": {"판정": verdict, "결정 기준": gate, "이유": why, "함정": trap}, "형식": "판정"},
                "원문": f"A형 채점 열쇠({did}) 기준으로 코드가 판정", "source_page": page, "짝키": f"{did}|C"})

        # 1) 기본 사례: 모든 조건 충족 (경계값)
        trap = "기준혼동(TNF): 비-TNF 약인데 TNF 실패를 요구하면 틀림" if en not in TNF else ""
        extra = ("TNF 억제제 등 생물학제제는 사용한 적이 없다",) if en not in TNF else ()
        why = "모든 급여 조건 충족: " + "; ".join(x for x in [
            (activity(k["G3"], "pass") or ("", ""))[1], prior(k["G4"], "pass", r["disease"], ped)[1]] if x)
        if en not in TNF:
            why += "; TNF 억제제 실패는 요구되지 않음"
        case("base", "전체", "예", why, extra=extra, trap=trap)

        # 2) 활성도 경계 미달 / 3) 활성도 점수 없음 → 판단 불가
        if k["G3"].get("척도"):
            case("act-low", "활성도", "아니오", activity(k["G3"], "fail")[1], act="fail", extra=extra)
            case("act-missing", "활성도", "판단 불가", activity(k["G3"], "missing")[1], act="missing", extra=extra)

        # 4) 이전 치료 부족 / 5) 내약성 없음 경로로도 인정
        case("prior-short", "이전 치료", "아니오", prior(k["G4"], "one", r["disease"], ped)[1], pr="one", extra=extra)
        clause = k["G4"].get("반응 조항", "")
        if ("불내성" in clause or "부작용" in clause) and not fistula:
            case("prior-intol", "이전 치료", "예", prior(k["G4"], "intolerance", r["disease"], ped)[1], pr="intolerance", extra=extra)

        # 6) 연령 하한 (원문에 직접 적힌 경계만)
        if age_min and not ped:
            case("age-low", "나이", "아니오", f"만 {age_min}세 이상이어야 함 ({age_min - 1}세)", age=age_min - 1, extra=extra)

        # 7) 고령·고위험
        if jak:
            case("old-nobio", "고령·고위험", "아니오", "65세 이상은 기존 생물학제제에 반응 없거나 내약성 없는 경우에만", age=68, extra=extra,
                 trap="")
            case("old-biofail", "고령·고위험", "예", "65세 이상이지만 생물학제제(아달리무맙) 실패 이력 있음",
                 age=68, extra=("아달리무맙(TNF 억제제)에 적절한 반응이 없었다",))
        elif k.get("G5", {}).get("조항") is False:
            case("old-control", "고령·고위험", "예", "이 약은 가이드북에 고령·고위험 추가 조건이 없음", age=68, extra=extra,
                 trap="대조: 고령 조건이 없는 약에 JAK 억제제의 65세 조건을 적용하면 틀림")

        # 8) 검사 하한 (Hb)
        if "G6-hb" in labs:
            hb_min = labs["G6-hb"]["값"]
            if hb_min > 8.5:
                case("hb-low", "검사 하한", "아니오", f"Hb {hb_min:g} g/dL 이상 필요 (8.5)", lab_over=8.5, extra=extra,
                     trap="약 비교: 같은 Hb 8.5에서 Filgotinib·Upadacitinib(하한 8)은 인정")
            else:
                case("hb-85", "검사 하한", "예", f"Hb 하한 {hb_min:g} g/dL → 8.5는 충족", lab_over=8.5, extra=extra,
                     trap="약 비교: 같은 Hb 8.5에서 Tofacitinib(하한 9)은 불인정")
                case("hb-low", "검사 하한", "아니오", f"Hb {hb_min:g} g/dL 이상 필요 (7.5)", lab_over=7.5, extra=extra)

        if "G6-anc" in labs:
            m = int(labs["G6-anc"]["값"])
            case("anc-low", "검사 하한", "아니오", f"ANC {m:,} cells/mm³ 이상 필요 ({m - 100:,})", anc=m - 100, extra=extra)
        if "G6-alc" in labs:
            m = int(labs["G6-alc"]["값"])
            case("alc-low", "검사 하한", "아니오", f"ALC {m:,} cells/mm³ 이상 필요 ({m - 50:,})", alc=m - 50, extra=extra)

        # 9) 유지요법 인정 / 불인정 / 판단 불가
        if "E" in k:
            ok = maintenance(k["E"], True)
            ng = maintenance(k["E"], False)
            if ok:
                case("maint-ok", "유지 기준", "예", ok[1], maint=ok[0])
                case("maint-ng", "유지 기준", "아니오", ng[1], maint=ng[0])
                t = k["E"].get("시점", "평가 시점")
                if k["E"]["종류"] not in seen_maint_missing:  # 반응 평가 종류(CDAI·PCDAI·PUCAI·Mayo·누공·DAIBD)마다 1문항
                    seen_maint_missing.add(k["E"]["종류"])
                    case("maint-missing", "유지 기준", "판단 불가", "평가 결과가 제시되지 않아 유지 기준 충족 여부를 판단할 수 없음",
                         maint=f"{t} 평가 결과는 이 사례에 제시되지 않았다")
    return out


def main() -> int:
    keys, names, rows = load()
    items = make(keys, names, rows)
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), "id 중복"
    qs = [i["question"] for i in items]
    assert len(qs) == len(set(qs)), "질문 중복"
    (OUT / "c_items.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    summ = {"문항": len(items), "판정별": dict(Counter(i["answer"]["정답"] for i in items)),
            "결정 기준별": dict(Counter(i["gate"] for i in items)),
            "함정 문항": sum(1 for i in items if i["answer"]["채점"]["함정"]),
            "약·적응증 행": len({i["drug_id"] for i in items}), "만든 날": "2026-11-12",
            "API": "사용 안 함 (A형 채점 열쇠로 코드가 판정)"}
    (OUT / "c_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
