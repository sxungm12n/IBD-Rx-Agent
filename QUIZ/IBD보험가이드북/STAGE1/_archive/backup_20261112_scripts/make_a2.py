#!/usr/bin/env python3
"""STAGE1 — A2형: A형이 묻지 않은 급여 규칙을 CSV 메모(notes)에서 뽑아 만든다 (2026-11-11).

A형과 같은 원칙
  - 정답은 코드가 CSV에서 그대로 가져온다. LLM은 쓰지 않는다 (OpenAI API 호출 없음).
  - 정답의 핵심 구절이 CSV 원문에 그대로 있는지 확인하고, 없으면 멈춘다.
  - 같은 정답을 여러 약 이름으로 반복하지 않도록, 약과 무관한 일반 규칙은 '일반' 문항 1개로 만든다.

영역
  R  휴약 후 재투여 인정 (p.58, 일반 규칙)
  P  교체 투여·처방량 (p.59, 일반 규칙)
  T  혈중농도·항체 검사 급여 (p.11·12, 일반 규칙)
  W  다른 약에서 이 약으로 교체투여(스위치) 급여 조건 (약별)
  L  장기 처방 기간 (약별)
  J  자가주사 투약 일지 (약별)
  D  용량 증량·연장 치료 (약별, 허가사항 기반 → '외국 기준과 같을 수 있는' 대조 영역)
사용: python3 STAGE1/make_a2.py   → output/a2_items.jsonl, output/a2_summary.json
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE.parents[2] / "data" / "IBD보험가이드북.csv"
OUT = HERE / "output"

sys.path.insert(0, str(HERE))
import make_a as A  # noqa: E402  (약 이름 규칙을 A형과 같게)


class SourceError(Exception):
    pass


def rows() -> list[dict]:
    raw = CSV_PATH.read_bytes().decode("utf-8-sig")
    return [{k.strip(): (v or "") for k, v in r.items()} for r in csv.DictReader(io.StringIO(raw))]


def tag(notes: str, name: str) -> str | None:
    m = re.search(r"\[" + re.escape(name) + r"\]([^\[]*)", notes)
    return m.group(1).strip().rstrip("/").strip() if m else None


def must_contain(text: str, *phrases: str) -> None:
    norm = re.sub(r"\s+", "", text)
    for p in phrases:
        if re.sub(r"\s+", "", p) not in norm:
            raise SourceError(f"정답 구절이 원문에 없음: {p!r}")


def item(iid, gate, crit, drug_id, drug_name, question, answer, key, source, page, cls=""):
    return {"id": iid, "type": "A2", "gate": gate, "기준": crit, "drug_id": drug_id, "drug_class": cls,
            "drug_name": drug_name, "question": question,
            "answer": {"정답": answer, "채점": key, "형식": "단답"}, "원문": source, "source_page": page,
            "짝키": f"{drug_id}|{gate}"}


# ---------------------------------------------------------------- 일반 규칙 (약 무관, 문항 1번씩)


def general(rs: list[dict]) -> list[dict]:
    out = []
    redo = {tag(r["notes"], "재투여(p.58)") for r in rs} - {None}
    sw = {tag(r["notes"], "교체·처방(p.59)") for r in rs} - {None}
    tdm = {tag(r["notes"], "TDM(p.11)") for r in rs} - {None}
    ab = {tag(r["notes"], "항-Infliximab 항체검사(p.12)") for r in rs} - {None}
    for s, what in ((redo, "재투여"), (sw, "교체·처방"), (tdm, "TDM"), (ab, "항체검사")):
        if len(s) != 1:
            raise SourceError(f"{what} 일반 규칙이 행마다 다름: {len(s)}가지")
    redo, sw, tdm, ab = redo.pop(), sw.pop(), tdm.pop(), ab.pop()

    q = "[생물학제제·소분자제제 공통, 가이드북 p.58] "
    must_contain(redo, "최초평가 실시 이전에 휴약한 환자의 재 투여는 최초 투여 인정기준에 해당 시 인정")
    out.append(item("A2-GEN-R1", "R", "재투여", "GEN", "공통", q + "최초 평가를 하기 전에 휴약한 환자를 다시 투여할 때 급여 인정 조건은?",
                    "최초 투여 인정기준에 해당하면 인정", {"필수 요소": ["최초 투여 인정기준 충족"]}, redo, "p.58"))
    must_contain(redo, "휴약기간이 3개월 미만이면 연속 투여로 인정")
    out.append(item("A2-GEN-R2", "R", "재투여", "GEN", "공통", q + "최초 평가 후 지속 투여 중 휴약한 환자의 휴약기간이 3개월 미만이면 어떻게 인정되는가?",
                    "연속 투여로 인정", {"필수 요소": ["연속 투여로 인정"]}, redo, "p.58"))
    must_contain(redo, "휴약기간이 3개월 이상이면", "마지막 평가 결과와 비교하여 20%이상 악화된 경우 인정", "마지막 평가 자료가 없으면 최초 투여 인정기준에 해당 시 인정")
    out.append(item("A2-GEN-R3", "R", "재투여", "GEN", "공통", q + "최초 평가 후 지속 투여 중 휴약한 환자의 휴약기간이 3개월 이상이면 재투여 인정 조건은?",
                    "마지막 평가 결과보다 20% 이상 악화된 경우 인정. 마지막 평가 자료가 없으면 최초 투여 인정기준에 해당 시 인정",
                    {"필수 요소": ["마지막 평가 대비 20% 이상 악화", "평가 자료 없으면 최초 투여 인정기준"], "값": 20, "단위": "%"}, redo, "p.58"))
    must_contain(redo, "의학적 사유(감염 등)로 평가하지 못한 경우는 4주 이내에 평가")
    out.append(item("A2-GEN-R4", "R", "재투여", "GEN", "공통", q + "평가 시점에 감염 등 의학적 사유로 평가하지 못하면 언제까지 평가해야 하는가?",
                    "4주 이내", {"필수 요소": ["4주 이내"], "값": 4, "단위": "주"}, redo, "p.58"))

    q = "[생물학제제·소분자제제 공통, 가이드북 p.59] "
    must_contain(sw, "교체한 약제는 최소 6개월 투여 유지 권고")
    out.append(item("A2-GEN-P1", "P", "교체·처방", "GEN", "공통", q + "다른 약제로 교체 투여한 경우, 교체한 약제를 최소 얼마 동안 유지하도록 권고하는가?",
                    "최소 6개월", {"필수 요소": ["최소 6개월"], "값": 6, "단위": "개월"}, sw, "p.59"))
    must_contain(sw, "최대 처방량은 1개월", "최초 투여일로부터 6개월 이후 안정된 질병 활성도를 보이고 부작용이 없는 환자에게 최대 2~3개월 처방")
    out.append(item("A2-GEN-P2", "P", "교체·처방", "GEN", "공통", q + "최대 처방량은? 더 길게 처방할 수 있는 조건이 있다면 무엇인가?",
                    "최대 1개월. 최초 투여일로부터 6개월 이후 안정된 질병 활성도를 보이고 부작용이 없으면 최대 2~3개월",
                    {"필수 요소": ["기본 최대 1개월", "6개월 이후 안정·부작용 없음", "최대 2~3개월"]}, sw, "p.59"))

    must_contain(tdm, "다른 약제로 교체 투여 고려 시 최초 1회에 대하여 요양 급여를 인정", "본인부담률을 80%로 적용")
    out.append(item("A2-GEN-T1", "T", "검사 급여", "GEN", "공통",
                    "[항TNF 제제 공통, 가이드북 p.11] Infliximab·Adalimumab 사용 중 혈중농도 검사(TDM)는 언제, 몇 회 급여가 인정되는가? 초과하면?",
                    "다른 약제로 교체 투여를 고려할 때 최초 1회 급여 인정. 초과 시 본인부담률 80%",
                    {"필수 요소": ["교체 투여 고려 시", "최초 1회", "초과 시 본인부담 80%"]}, tdm, "p.11"))
    must_contain(ab, "혈중농도가 3.0㎍/mL미만으로 확인되어 실시한 경우 요양 급여를 인정", "본인부담률을 80%로 적용")
    out.append(item("A2-GEN-T2", "T", "검사 급여", "GEN", "공통",
                    "[Infliximab, 가이드북 p.12] 항-Infliximab 항체검사는 어떤 경우에 급여가 인정되는가? 인정 횟수를 초과하면?",
                    "Infliximab 혈중농도가 3.0 ㎍/mL 미만으로 확인되어 실시한 경우 인정. 초과 시 본인부담률 80%",
                    {"필수 요소": ["혈중농도 3.0 ㎍/mL 미만 확인", "초과 시 본인부담 80%"], "값": 3.0, "단위": "㎍/mL"}, ab, "p.12"))
    return out


# ---------------------------------------------------------------- 약별 규칙


def per_drug(rs: list[dict]) -> list[dict]:
    routes: dict = {}
    sib: dict = {}
    for r in rs:
        routes.setdefault(r["drug_en"], set()).add(r["route"])
        sib.setdefault((r["drug_en"], r["route"], r["disease"]), set()).add(r["age_group"])
    multi = {n for n, v in routes.items() if len(v) > 1}
    out = []
    for r in rs:
        row = A.Row(r)
        name = A.drug_name(row, multi, sib)
        did, cls, page = r["drug_id"], r["drug_class"], r["source_page"]
        notes = r["notes"]

        sw = tag(notes, "스위치")
        if sw:
            m = re.match(r"(.+?)에 효과 없거나 부작용으로 지속 불가 또는 복약순응도 개선 필요 시", sw)
            if not m:
                raise SourceError(f"{did}: 스위치 문장 형식이 다름")
            prior = m.group(1)
            must_contain(sw, "최소 6개월", "소견서")
            out.append(item(f"A2-{did}-W", "W", "교체투여(스위치)", did, name,
                            f"[{name}] 다른 약에서 이 약으로 교체투여(스위치)할 때 급여가 인정되는 조건은?",
                            f"{prior}에 효과 없거나, 부작용으로 지속할 수 없거나, 복약순응도 개선이 필요한 경우. 교체투여 소견서 첨부 필요(교체 약제는 최소 6개월 유지 권고)",
                            {"필수 요소": ["이전 약제 목록", "효과 없음 / 부작용으로 지속 불가 / 복약순응도 개선 필요", "소견서 첨부"],
                             "이전 약제": prior, "참고(필수 아님)": "최소 6개월 유지 권고"}, sw, page, cls))

        # 처방 기간: 정맥주사(IV) 행은 건너뛴다 (IV 행에 붙은 문구는 피하주사 제품(프리필드펜)에 대한 것)
        parts = [t for t in (tag(notes, "장기처방"), tag(notes, "장기처방(p.23)"), tag(notes, "장기처방(p.26)"), tag(notes, "처방(p.28)")) if t]
        if parts and r["route"] != "IV":
            lt = " / ".join(parts)
            ans, req = [], []
            if "퇴원 시 최대 2주분, 외래 최대 4주분" in lt:
                must_contain(lt, "24주", "8~12주분")
                ans.append("퇴원 시 최대 2주분, 외래 최대 4주분(원내처방 원칙). 최초 투약 24주 이후 안정·부작용 없으면 최대 8~12주분")
                req += ["퇴원 최대 2주분", "외래 최대 4주분", "24주 이후 안정 시 최대 8~12주분"]
            if "퇴원할 경우 최대 2주분" in lt:
                ans.append("퇴원할 경우 최대 2주분 원내 처방 원칙")
                req += ["퇴원 시 최대 2주분 원내 처방"]
            if re.search(r"24주 이 ?후, 12주 분", lt):
                ans.append("SC 제형 투여 24주 이후 12주분 장기 처방 가능(자가투여일지 작성)")
                req += ["24주 이후 12주분 장기 처방"]
            if not ans:
                raise SourceError(f"{did}: 처방 기간 문장 형식이 다름: {lt[:60]}")
            out.append(item(f"A2-{did}-L", "L", "처방 기간", did, name,
                            f"[{name}] 1회 처방 기간(장기 처방) 한도는?", ". ".join(ans), {"필수 요소": req}, lt, page, cls))

        sj = tag(notes, "자가주사")
        if sj:
            must_contain(sj, "투약 일지", "요양기관 관리")
            out.append(item(f"A2-{did}-J", "J", "자가주사", did, name,
                            f"[{name}] 자가주사 제제로 처방할 때 가이드북이 요구하는 관리 조건은?",
                            "환자용 투약 일지를 환자가 작성하고 요양기관이 관리", {"필수 요소": ["환자 투약 일지 작성", "요양기관 관리"]},
                            sj, page, cls))

        esc = tag(notes, "증량")
        if esc and "해당 없음" not in esc:
            # 증량 문장 뒤에 이상반응 칸이 ' / '로 이어붙어 있다 → 이상반응이 시작되는 조각부터 버린다
            ae = ("주입반응", "주사부위", "피부병변", "드물게", "감염", "다리 정맥", "중성구", "여드름", "어지러움", "ALT")
            keep = []
            for seg in esc.split(" / "):
                if seg.strip().startswith(ae):
                    break
                keep.append(seg.strip())
            body = " / ".join(keep).strip()
            # 성인·소아 문장이 한 칸에 같이 있으면 행의 연령군에 맞는 쪽만
            m = re.search(r"\.\s*(소아)", body)
            if body.startswith("성인:") and m:
                body = body[m.start(1):] if r["age_group"] == "pediatric" else body[:m.start()].strip() + "."
            body = re.sub(r"^(성인|IV):\s*", "", body).strip()
            must_contain(esc, body.rstrip("."))
            out.append(item(f"A2-{did}-D", "D", "용량 증량·연장", did, name,
                            f"[{name}] 반응이 부족하거나 감소할 때 가이드북에 적힌 용량 증량·간격 단축·연장 치료 방법은?",
                            body, {"필수 요소": ["증량 용량·간격·기간"], "비고": "허가사항 기반 내용 (한국·외국 기준 일치 가능 영역)"},
                            esc, page, cls))
    return out


def main() -> int:
    rs = rows()
    try:
        items = general(rs) + per_drug(rs)
    except SourceError as e:
        print("멈춤:", e, file=sys.stderr)
        return 1
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), "id 중복"
    OUT.mkdir(exist_ok=True)
    (OUT / "a2_items.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    from collections import Counter
    uniq = {(i["gate"], i["answer"]["정답"]) for i in items}
    summ = {"문항": len(items), "고유 정답": len(uniq), "영역별": dict(Counter(i["기준"] for i in items)),
            "만든 날": "2026-11-11", "API": "사용 안 함 (CSV 원문에서 코드로 생성)"}
    (OUT / "a2_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
