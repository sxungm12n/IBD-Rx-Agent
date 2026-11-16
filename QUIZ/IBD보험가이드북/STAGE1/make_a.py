#!/usr/bin/env python3
"""STAGE1 — A형: 급여 기준을 묻는 서술형 문항을 보험가이드북 CSV에서 만든다.

이 파일 하나로 돈다 (파이썬 표준 라이브러리만, 모델 호출 없음).

    python3 STAGE1/make_a.py              # 자체 시험 → 문항 생성
    python3 STAGE1/make_a.py --csv 경로    # 다른 CSV

원칙
  - 보기 없이 답을 직접 쓰게 한다 (찍을 수 없게)
  - 정답은 원문 칸에 적힌 그대로 따른다. 숫자·이상/초과를 못 읽거나 두 가지로 읽히면 멈춘다 (기본값 없음)
  - 같은 칸을 다른 방법으로 다시 확인한다 (원문 대조)
  - 원문 대조가 실제로 오류를 잡는지, 실행할 때마다 일부러 망가뜨린 CSV로 먼저 시험한다

결과 (STAGE1/output/)
  a_items.jsonl  문항 (정답 문장 + 채점 열쇠)
  a_review.csv   검수 양식 (엑셀)
  summary.json   개수, 고유 정답 수, CSV 해시
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"
# STAGE1 → IBD보험가이드북 → QUIZ → IBD Rx Agent
DEFAULT_CSV = HERE.parents[2] / "data" / "IBD보험가이드북.csv"

DISEASE_KO = {"CD": "크론병", "UC": "궤양성 대장염", "GIBD": "장형 베체트", "CD/UC": "크론병·궤양성 대장염"}
AGE_KO = {"adult": "성인", "pediatric": "소아", "fistulizing": "누공성", "all": "", "": ""}
OPERATOR = {"≥": "이상", ">": "초과", "이상": "이상", "초과": "초과"}

GATE_NAME = {"G2": "나이", "G3": "활성도", "G4": "이전 치료", "G5": "고령·고위험 조건", "G6": "검사 하한", "G7": "금기", "E": "유지 기준"}
QUESTION = {
    "G2": "[{약}] 가이드북에 적힌 연령(체중) 조건은?",
    "G3": "[{약}] 급여 활성도 기준은?",
    "G4": "[{약}] 어떤 이전 치료에 실패해야 급여되는가?",
    "G5": "[{약}] 65세 이상·심혈관계 고위험군·악성 종양 위험 환자에게 쓸 때 붙는 추가 급여 조건이 있는가? 있다면 무엇인가?",
    "G6": "[{약}] {검사} 하한은?",
    "G7": "[{약}] 가이드북에 표시된 이 약의 투여 금기는?",
    "G7-체크리스트": "[{약}] 가이드북의 투여 전 체크리스트 항목을 모두 쓰시오.",
    "E": "[{약}] 유지요법은 언제, 어떤 조건에서 인정되는가?",
    "E-시점없음": "[{약}] 유지요법은 어떤 조건에서 인정되는가?",
}

# 원문에 나이가 직접 적힌 경계만 (성인 19세·소아 18세는 운영 규칙이라 묻지 않는다)
SOURCE_AGE = {
    "MESA-CD-PED": {"min": 6, "page": "p.17"},
    "MESA-UC-PED": {"min": 6, "page": "p.17"},
    "MESA-PR-UC-PED": {"min": 10, "weight_gt": 50, "page": "p.17"},
    "BAL-UC-PED": {"min": 5, "max": 17, "page": "p.17"},
    "IFX-IV-UC-ped": {"max": 18, "page": "p.36"},
    "IFX-IV-GIBD": {"min": 19, "page": "p.37"},
}
# 같은 질환에서 나이 조건이 "없는" 것을 묻는 대조 문항 (IFX 베체트는 만 19세, ADA 베체트는 조건 없음)
AGE_NONE = {"ADA-GIBD"}
# 고령·고위험 조항이 "없는" 것을 묻는 대조 문항 (UC 소분자 중 JAK가 아닌 약)
G5_NONE = {"OZA-UC", "VEDO-IV-UC", "UST-CD"}
# 평가 시점이 원문끼리 달라 시점은 묻지 않는 행 (notes의 [원문 상이])
TIMING_CONFLICT = {"VEDO-SC-CD", "VEDO-SC-UC", "OZA-UC"}
# 쪽마다 다른 시점 중 고시문(eval_week)을 정답으로, 다른 쪽 문구는 '함께 써도 정답' (결정 3, 2026-11-11; PDF 원본 대조)
TIMING_ALT = {
    "VEDO-SC-CD": "300mg IV 최소 2회 투약 후 평가 (p.29 투약간격 그림)",
    "VEDO-SC-UC": "300mg IV 최소 2회 투약 후 평가 (p.29 투약간격 그림)",
    "OZA-UC": "치료 시작 10~22주 후 (p.27 비교표)",
    "IFX-IV-CD-fistula": "14주 이내 (p.23 비교표 'FCD: 3회 투약 후, 14주 이내')",
}
# 고령·고위험 대조(함정) 문항에서 체크리스트의 심혈관 병력 조건을 인용하는 것은 지어낸 조건이 아니다
G5_NONE_ALT = {
    "OZA-UC": "투여 전 체크리스트의 '최근 6개월 이내 심근경색·불안정협심증·뇌졸중·일과성 허혈발작·비대상성 심부전 병력 없음' "
              "(급여 추가 조건이 아니라 투여 전 확인사항)",
}

MAINTENANCE = {
    # 종류: (정답 문장, 원문이 반드시 맞아야 하는 표현, 채점 열쇠)
    "CDAI": ("CDAI 70점 이상 감소 또는 25% 이상 감소",
             [r"70\s*점\s*이상\s*감소\s*또는[^.]*?25\s*%\s*이상\s*감소"],
             {"절대 감소": 70, "상대 감소(%)": 25, "결합": "또는"}),
    "PCDAI": ("PCDAI 12.5점 이상 감소 또는 25% 이상 감소",
              [r"12\.5\s*점\s*이상\s*감소\s*또는[^.]*?25\s*%\s*이상\s*감소"],
              {"절대 감소": 12.5, "상대 감소(%)": 25, "결합": "또는"}),
    "PUCAI": ("PUCAI 20점 이상 감소", [r"20\s*점\s*이상\s*감소"], {"절대 감소": 20}),
    "DAIBD": ("DAIBD 20점 이상 감소", [r"20\s*점\s*이상\s*감소"], {"절대 감소": 20}),
    "fistula": ("누공 개수 50% 이상 감소", [r"50\s*%\s*이상\s*감소"], {"상대 감소(%)": 50}),
    "Mayo": ("Mayo 30% 이상 그리고 3점 이상 감소, 그리고 직장출혈 점수 1점 이상 감소 또는 0~1점",
             [r"모두\s*충족",
              r"30\s*%\s*이상\s*감소하고\s*3\s*점\s*이상\s*감소",
              r"Rectal bleeding subscore\s*1\s*점\s*이상\s*감소\s*또는\s*Rectal bleeding subscore\s*0\s*점\s*또는\s*1\s*점"],
             {"상대 감소(%)": 30, "절대 감소": 3, "결합": "그리고", "직장출혈": {"절대 감소": 1, "또는 점수": [0, 1]}}),
}
LAB = (("lab_hb_min", "hb", "Hb"), ("lab_anc_min", "anc", "ANC"), ("lab_alc_min", "alc", "ALC"))
CONTRA = (
    ("pregnancy_contra", "임신"),
    ("contra_active_infection", "활동성 감염"),
    ("contra_active_tb", "활동성 결핵"),
    ("contra_severe_hepatic", "중증 간장애"),
    ("contra_severe_renal", "말기 신장애"),
    ("contra_recent_cv_event", "최근 6개월 심혈관 사건"),
    ("contra_mao_inhibitor", "MAO 억제제 병용"),
    ("contra_immunomodulator", "면역조절제 병용"),
)


CHECKLIST_KEYWORD = {
    "임신": r"임부|임신",
    "활동성 감염": r"감염",
    "활동성 결핵": r"결핵",
    "중증 간장애": r"간장애|Child-Pugh",
    "말기 신장애": r"신장애|CrCl",
    "최근 6개월 심혈관 사건": r"심근경색|심혈관",
    "MAO 억제제 병용": r"MAO",
    "면역조절제 병용": r"면역조절제",
    "심전도 이상": r"ECG|방실차단",
}


class SourceError(ValueError):
    """원문에서 기준을 하나로 읽을 수 없다."""


# ---------------------------------------------------------------- CSV


class Row:
    def __init__(self, data: dict[str, str]):
        self.data = data

    def get(self, key: str) -> str:
        return (self.data.get(key) or "").strip()

    def yes(self, key: str) -> bool:
        return self.get(key).startswith("Y")

    @property
    def drug_id(self) -> str:
        return self.get("drug_id")


def load_rows(path: Path) -> tuple[list[Row], str]:
    raw = path.read_bytes()
    rows = [Row({k.strip(): v for k, v in row.items()}) for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))]
    return [row for row in rows if row.drug_id], hashlib.sha256(raw).hexdigest()


def number(text: str) -> float:
    return float(text.replace(",", ""))


def show(value: float) -> str:
    return f"{value:g}"


# ---------------------------------------------------------------- 기준 읽기 (각각 정답 + 채점 열쇠)


def not_written(what: str, detail: str = "") -> str:
    """'없다'가 아니라 '가이드북에 적혀 있지 않다'로만 쓴다 (CSV의 N·빈칸 = 적혀 있지 않음). 모든 대조 정답이 이 함수를 거친다."""
    return f"{what} 가이드북에 적혀 있지 않다" + (f" ({detail})" if detail else "")


def strip_csv_memo(text: str) -> str:
    """CSV를 옮긴 사람이 붙인 메모('★…')는 원문이 아니므로 정답에서 뺀다."""
    text = re.sub(r"\s*\(★[^)]*\)", "", text)
    if "★" in text:
        raise SourceError(f"괄호 밖의 CSV 메모(★)를 정답에서 뺄 수 없음: {text!r}")
    return text


def only_one(matches: list, what: str):
    distinct = {tuple(match) if isinstance(match, (list, tuple)) else match for match in matches}
    if not distinct:
        raise SourceError(f"{what}을 찾지 못함")
    if len(distinct) > 1:
        raise SourceError(f"{what}이 두 가지 이상으로 읽힘: {sorted(distinct)}")
    return next(iter(distinct))


def read_activity(row: Row) -> tuple[str, dict] | None:
    scale = row.get("activity_scale")
    text = row.get("activity_threshold")
    # '누공이 없는 경우'는 평가방법의 소제목이라 정답 요소가 아니다. 써도 정답으로만 둔다.
    optional = ["누공 없는 경우"] if "누공 없는 경우" in text else []
    if scale in {"CDAI", "PCDAI"}:
        prefix = r"(?<!P)CDAI" if scale == "CDAI" else r"PCDAI"
        found = re.findall(prefix + r"\s*(≥|>)\s*(\d+(?:\.\d+)?)", text)
        found += [(op, value) for value, op in re.findall(prefix + r"\s*(\d+(?:\.\d+)?)\s*(이상|초과)", text)]
        op, value = only_one(found, f"{scale} 기준")
        answer = f"{scale} {show(number(value))} {OPERATOR[op]}"
        key = {"척도": scale, "값": number(value), "비교": OPERATOR[op]}
        if optional:
            key["함께 써도 정답"] = optional
        return answer, key
    if scale == "PUCAI":
        op_value = re.findall(r"PUCAI[^\d]{0,80}?(\d+)\s*(초과|이상)", text)
        value, op = only_one(op_value, "PUCAI 기준")
        return f"PUCAI {value} {op}", {"척도": "PUCAI", "값": number(value), "비교": op}
    if scale == "Mayo+Endo":
        low, high, joint, op, endo = only_one(
            re.findall(r"Mayo score\s*(\d+)\s*[~-]\s*(\d+)\s*(and|그리고|및)\s*Endoscopy subscore\s*(≥|>)\s*(\d+)", text),
            "Mayo 범위 '그리고' 내시경 기준",
        )
        answer = f"Mayo {low}~{high} 그리고 내시경 subscore {endo} {OPERATOR[op]}"
        return answer, {"척도": "Mayo+Endo", "Mayo": [number(low), number(high)], "결합": "그리고", "내시경": number(endo), "내시경비교": OPERATOR[op]}
    if scale == "DAIBD" or ("장 궤양" in text and not scale):
        if "장 궤양" not in text:
            raise SourceError("베체트 행인데 장 궤양 조건이 없음")
        return not_written("활성도 점수 기준은"), {"척도": None, "함께 써도 정답": {"대상": "베체트병 진단 + 내시경 등으로 장 궤양이 확인된 경우"}}
    if not scale and "누공성" in text:
        return not_written("활성도 점수 기준은"), {"척도": None, "함께 써도 정답": {"대상": "보편적 치료에 반응 없는 누공성 크론병"}}
    if scale:
        raise SourceError(f"알 수 없는 활성도 척도 {scale}")
    return None


def conventional_source(row: Row) -> str:
    return " / ".join(part for part in (row.get("activity_threshold"), row.get("prior_bio_note")) if part)


def read_conventional(row: Row) -> tuple[str, dict] | None:
    if row.get("prior_conventional") != "Y":
        return None
    text = conventional_source(row)
    spans = re.findall(r"보편적\s*치료\([^)]*\)", text) + re.findall(r"Corticosteroid나[^.;/]*?보편적\s*치료", text)
    # 활성도 칸과 prior_bio_note에 같은 구절이 구분점(·)과 쉼표만 다르게 적힌 경우는 하나로 본다
    canonical = {re.sub(r"\s*[,·]\s*", "·", item): item for item in reversed(spans)}
    span = only_one(list(canonical), "보편적 치료 요건")
    span = canonical[span]
    inside = re.sub(r"^.*?\(|\)$", "", span) if "(" in span else span
    if "2가지" in text and "2가지" not in span:
        raise SourceError("원문에 '2가지'가 있는데 보편적 치료 구절 밖에 있음")
    note = row.get("prior_bio_note")
    if re.search(r"보편적인?\s*치료", note) and ("2가지" in note) != ("2가지" in span):
        raise SourceError("prior_bio_note와 활성도 칸의 '2가지' 조건이 다름")
    therapies = [part.strip() for part in re.split(r"[·,]| 또는 |나 ", re.sub(r"(2가지 이상(의 치료법)?:|적어도 2가지 이상|등|보편적\s*치료|Exclusive enteral nutrition)", "", inside)) if part.strip()]
    key = {"최소 가지 수": 2 if "2가지" in span else None, "치료": therapies}
    # 뒤따르는 원문(반응 없거나 내약성 없거나 금기 / 반응이 없는 / 부작용 등으로 치료 중단한)을 그대로 붙인다
    tail = re.search(re.escape(span) + r"(\s*(?:약제)?에\s*.*?(?:금기|없는|중단한|중단))", text)
    if not tail:
        raise SourceError("보편적 치료 구절 뒤의 '반응 없음' 조건을 읽지 못함")
    clause = tail.group(1)
    key["반응 조항"] = "반응 없음·부작용 중단" if "중단" in clause else ("반응 없음·불내성·금기" if "금기" in clause else "반응 없음")
    ending = " 경우" if clause.endswith(("없는", "중단한")) else ""
    return span + clause + ending, key


def read_high_risk(row: Row) -> tuple[str, dict] | None:
    if row.drug_id in G5_NONE:
        text = row.get("prior_bio_note") + row.get("activity_threshold") + row.get("notes")
        if row.get("prior_biologic") == "conditional" or any(word in text for word in ("65세", "심혈관", "악성")):
            raise SourceError("대조 문항인데 고령·고위험 조항이 있음")
        key = {"조항": False}
        if row.drug_id in G5_NONE_ALT:
            key["함께 써도 정답"] = G5_NONE_ALT[row.drug_id]
        return not_written("65세 이상·심혈관계 고위험군·악성 종양 위험 환자에 대한 추가 급여 조건은"), key
    if row.get("prior_biologic") != "conditional":
        return None
    note = row.get("prior_bio_note")
    for word in ("65세", "심혈관", "악성", "생물학제제", "한하여"):
        if word not in note:
            raise SourceError(f"고령·고위험 조항에 '{word}'가 없음")
    # 질문이 세 대상을 모두 묻는다 → 세 대상 모두 필수 (결정 4, 2026-11-11. 이전 판은 65세만 묻고 65세만 필수였다)
    return note, {"조항": True, "대상": ["65세 이상", "심혈관계 고위험", "악성종양 위험"], "조건": "생물학제제 실패·불내성 후에만"}


def read_age(row: Row) -> tuple[str, dict] | None:
    if row.drug_id in AGE_NONE:
        if row.get("age_min") or row.get("age_max") or re.search(r"\d+\s*세", row.get("activity_threshold")):
            raise SourceError("대조 문항인데 나이 조건이 있음")
        return not_written("연령 조건은"), {"min": None, "max": None}
    rule = SOURCE_AGE.get(row.drug_id)
    if not rule:
        return None
    if rule.get("min") is not None and row.get("age_min") != str(rule["min"]):
        raise SourceError(f"age_min {row.get('age_min')} ≠ 원문 경계 {rule['min']}")
    if rule.get("max") is not None and row.get("age_max") != str(rule["max"]):
        raise SourceError(f"age_max {row.get('age_max')} ≠ 원문 경계 {rule['max']}")
    if rule.get("weight_gt") and not re.search(rf"체중\s*{rule['weight_gt']}\s*kg\s*초과", row.get("activity_threshold")):
        raise SourceError("체중 조건이 원문 칸에 없음")
    low, high = rule.get("min"), rule.get("max")
    blob = " ".join(row.data.values())
    phrase = (
        rf"{low}\s*[~-]\s*{high}\s*세" if low is not None and high is not None
        else (rf"만?\s*{low}\s*세\s*이상" if low is not None else rf"{high}\s*세\s*이하")
    )
    if not re.search(phrase, blob):
        raise SourceError(f"원문 문구에 나이 경계({phrase})가 없음")
    answer = f"{low}~{high}세" if low is not None and high is not None else (f"{low}세 이상" if low is not None else f"{high}세 이하")
    if rule.get("weight_gt"):
        answer += f", 체중 {rule['weight_gt']}kg 초과"
    key = {"min": low, "max": high, "체중초과": rule.get("weight_gt")}
    if low is not None and high is None and row.get("age_group") == "pediatric":
        key["함께 써도 정답"] = {"max": 18, "이유": "소아 행 운영 규칙"}
    return answer, key


def read_lab(text: str) -> tuple[str, dict]:
    """단위가 붙은 값만 읽는다. 서로 다른 값이 둘 이상이면 멈춘다."""
    found = []
    for value in re.findall(r"(\d+(?:\.\d+)?)\s*g/dL", text):
        found.append(("g/dL", number(value), f"{value} g/dL"))
    for value in re.findall(r"(\d+(?:\.\d+)?)\s*[×x]\s*10[⁹9]?\s*(?:cells/L|/L)", text):
        found.append(("cells/mm³", number(value) * 1000, f"{value}×10⁹/L"))
    for value in re.findall(r"(\d{1,3}(?:,\d{3})+|\d+)\s*cells/mm³", text):
        found.append(("cells/mm³", number(value), f"{value} cells/mm³"))
    unit, value = only_one([(unit, value) for unit, value, _ in found], "검사 하한")
    original = next(raw for u, v, raw in found if (u, v) == (unit, value))
    if "미만 시" in text:
        compare = "이상"
    elif "이하 시" in text:
        compare = "초과"
    else:
        raise SourceError("검사 하한의 경계 방향(미만 시/이하 시)을 찾지 못함")
    answer = original if original.endswith(unit) else f"{original} (= {value:,.0f} {unit})"
    if compare == "초과":
        answer += " 초과"
    return answer, {"값": value, "단위": unit, "비교": compare}


def read_checklist(row: Row) -> tuple[list[str], dict] | None:
    """notes의 [투여 전 체크리스트 …] 항목을 그대로 꺼낸다. 있으면 금기 칸 대신 이것으로 묻는다.

    항목은 ①~⑩ 번호나 ' / '로 나뉘고, 다음 [소제목] 앞에서 끝난다.
    '※' 뒤 문장은 원문에서 체크리스트 아래 붙은 주의 문구라 항목이 아니다 → 채점 열쇠의 '함께 써도 정답'
    (써도 '정답에 없는 항목'으로 세지 않는다. '※ 65세 이상…' 고령·고위험 조항도 같은 쪽에 있으므로 여기에 넣는다).
    CSV 메모('(★…)')는 뺀다.
    """
    notes = row.get("notes")
    header = re.search(r"\[투여 전 체크리스트\s*-?\s*([^\]]*)\]", notes)
    if not header:
        return None
    body = re.split(r"\s+/\s+\[", notes[header.end():], maxsplit=1)[0]
    # 항목 구분은 앞뒤에 띄어쓰기가 있는 ' / '뿐이다 (cells/mm³, g/dL의 '/'는 단위)
    pieces = re.split(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫]", body) if "①" in body else re.split(r"\s+/\s+", body)
    parts, remarks = [], []
    for piece in pieces:
        item, *notes_after = re.split(r"\.?\s*※\s*", piece)
        item = strip_csv_memo(item.strip().rstrip(".").strip())
        if item and not item.startswith("65세"):
            parts.append(item)
        if item.startswith("65세"):
            remarks.append(item)
        for remark in notes_after:
            remark = strip_csv_memo(remark.strip().rstrip(".").strip())
            if remark:
                remarks.append(remark)
    if len(parts) < 3:
        raise SourceError("체크리스트 항목을 읽지 못함")
    # 금기 칸(Y)마다 체크리스트에 해당 내용이 있어야 한다 (두 칸 대조)
    joined = " ".join(parts + remarks)
    for key, label in CONTRA + (("ecg_required", "심전도 이상"),):
        if row.yes(key) and not re.search(CHECKLIST_KEYWORD[label], joined):
            raise SourceError(f"금기 칸 '{label}'이 Y인데 체크리스트에 없음")
    key = {"항목": parts, "의미": header.group(1).strip()}
    if remarks:
        key["함께 써도 정답"] = remarks
    return parts, key


def read_contra(row: Row) -> tuple[list[str], dict] | None:
    items, labels = [], []
    for key, label in CONTRA:
        cell = row.get(key)
        if cell.startswith("Y"):
            detail = re.search(r"\((.*)\)", cell)
            items.append(f"{label} ({detail.group(1)})" if detail else label)
            labels.append(label)
    ecg = row.get("ecg_required")
    if ecg.startswith("Y") and "금기" not in ecg:
        raise SourceError("심전도 칸이 Y인데 금기 내용이 없음")
    if ecg.startswith("Y") and "금기" in ecg:
        detail = re.search(r"금기:\s*([^)]*)", ecg)
        if not detail:
            raise SourceError("심전도 금기 내용을 읽지 못함")
        items.append(f"심전도 이상 ({detail.group(1).strip()})")
        labels.append("심전도 이상")
    if not items:
        return None
    return items, {"항목": labels}


def maintenance_kind(row: Row) -> str:
    """척도 이름만으로 종류를 정한다. 숫자는 read_maintenance에서 따로 확인한다."""
    text = row.get("eval_criteria")
    if "PCDAI" in text:
        return "PCDAI"
    if re.search(r"(?<!P)CDAI", text):
        return "CDAI"
    if "PUCAI" in text:
        return "PUCAI"
    if "DAIBD" in text:
        return "DAIBD"
    if "누공" in text and "개수" in text:
        return "fistula"
    if "Mayo" in text:
        return "Mayo"
    return ""


def read_maintenance(row: Row) -> tuple[str, dict] | None:
    kind = maintenance_kind(row)
    if not kind:
        return None
    criterion, required, structure = MAINTENANCE[kind]
    for pattern in required:
        if not re.search(pattern, row.get("eval_criteria")):
            raise SourceError(f"유지 기준 원문이 예상 표현과 다름 (숫자·그리고/또는 확인): {pattern}")
    key = {"종류": kind, "기준": criterion, **structure}
    if row.drug_id in TIMING_CONFLICT and "[원문 상이]" not in row.get("notes"):
        raise SourceError("시점 상이 목록에 있는데 [원문 상이] 메모가 없음")
    timing = row.get("eval_week")
    if not timing:
        raise SourceError("평가 시점 칸이 비어 있음")
    # 평가 기준 문장에 시점이 적혀 있으면 eval_week와 같아야 한다
    in_criteria = re.findall(r"(\d+)\s*(주|회)", row.get("eval_criteria"))
    in_week = re.findall(r"(\d+)\s*(주|회)", timing)
    if in_criteria and not set(in_week) & set(in_criteria):
        raise SourceError(f"평가 시점 {timing}이 평가 기준 문장의 시점 {in_criteria}과 다름")
    key["시점"] = timing
    if row.drug_id in TIMING_ALT:
        key["함께 써도 정답"] = {"시점": TIMING_ALT[row.drug_id], "이유": "가이드북 다른 쪽의 시점 문구. 정답은 고시문 기준"}
    return f"{timing} 평가, {criterion}", key


# ---------------------------------------------------------------- 만들기


# 'IV→SC'가 정맥→피하 전환 용법을 묻는 것처럼 읽혀 제품명으로 쓴다 (결정 6, 2026-11-11)
ROUTE_NAME = {("Infliximab", "IV→SC"): "피하주사(램시마 SC)", ("Vedolizumab", "IV→SC"): "피하주사(킨텔레스 SC)"}


def drug_name(row: Row, multi_route: set[str], siblings: dict) -> str:
    ingredient = row.get("drug_en") or row.drug_id
    route = ROUTE_NAME.get((ingredient, row.get("route")), row.get("route"))
    head = f"{ingredient} {route}" if ingredient in multi_route else ingredient
    age = AGE_KO.get(row.get("age_group"), row.get("age_group"))
    # 같은 성분·경로·질환에 다른 연령군 행이 없으면 연령군을 쓰지 않는다 ('성인 장형 베체트'가 19세를 알려 주지 않게)
    if len(siblings[(row.get("drug_en"), row.get("route"), row.get("disease"))]) < 2:
        age = ""
    disease = DISEASE_KO.get(row.get("disease"), row.get("disease"))
    return f"{head}, {age + ' ' if age else ''}{disease}"


def silent_drop_check(row: Row) -> None:
    """원문에 기준이 적혀 있는데 판정 칸이 비어 문항이 빠지는 것을 막는다."""
    threshold = row.get("activity_threshold")
    if not row.get("activity_scale") and re.search(r"(CDAI|PUCAI|Mayo score|Endoscopy subscore)", threshold):
        raise SourceError("활성도 문장에 점수 기준이 있는데 activity_scale이 비어 있음")
    if row.get("prior_conventional") != "Y" and re.search(r"보편적인?\s*치료", threshold):
        raise SourceError("보편적 치료 조건이 적혀 있는데 prior_conventional이 Y가 아님")
    if row.drug_id not in G5_NONE and row.get("prior_biologic") != "conditional" and "65세" in threshold + row.get("prior_bio_note"):
        raise SourceError("65세 조항이 적혀 있는데 prior_biologic이 conditional이 아님")
    if row.get("activity_scale") and not threshold:
        raise SourceError("activity_scale은 있는데 활성도 문장이 비어 있음")
    ecg = row.get("ecg_required")
    if ecg.startswith("Y") and "금기" not in ecg:
        raise SourceError("심전도 칸이 Y인데 금기 내용이 없음")


def facts_of(row: Row) -> list[tuple[str, str, object, dict, str]]:
    """(기준, 검사 칸, 정답, 채점 열쇠, 원문 칸)."""
    silent_drop_check(row)
    found = []
    threshold = row.get("activity_threshold")
    for gate, reader, source in (
        ("G2", read_age, f"age_min={row.get('age_min') or '없음'}, age_max={row.get('age_max') or '없음'} / {threshold}"),
        ("G3", read_activity, threshold),
        ("G4", read_conventional, conventional_source(row)),
        ("G5", read_high_risk, row.get("prior_bio_note") or "(prior_bio_note 비어 있음)"),
    ):
        result = reader(row)
        if result:
            if gate == "G2" and row.drug_id in SOURCE_AGE:
                source = f"원문 {SOURCE_AGE[row.drug_id]['page']} — " + source
            found.append((gate, "", result[0], result[1], source))
    for key, attr, _ in LAB:
        if row.get(key):
            answer, scoring = read_lab(row.get(key))
            found.append(("G6", attr, answer, scoring, row.get(key)))
    checklist = read_checklist(row)
    if checklist:
        notes = row.get("notes")
        start = notes.index("[투여 전 체크리스트")
        source = "notes: " + re.split(r"\s+/\s+\[", notes[start:], maxsplit=1)[0]
        found.append(("G7", "체크리스트", checklist[0], checklist[1], source))
    else:
        result = read_contra(row)
        if result:
            source = "; ".join(f"{k}={row.get(k)}" for k, _ in CONTRA if row.yes(k))
            if row.get("ecg_required").startswith("Y"):
                source += f"; ecg_required={row.get('ecg_required')}"
            found.append(("G7", "", result[0], result[1], source))
    result = read_maintenance(row)
    if result:
        found.append(("E", "", result[0], result[1], f"{row.get('eval_week')} / {row.get('eval_criteria')}"))
    return found


def build(rows: list[Row]) -> tuple[list[dict], list[str]]:
    routes: dict[str, set[str]] = {}
    for row in rows:
        routes.setdefault(row.get("drug_en"), set()).add(row.get("route"))
    multi_route = {name for name, values in routes.items() if len(values) > 1}
    siblings: dict = {}
    for row in rows:
        siblings.setdefault((row.get("drug_en"), row.get("route"), row.get("disease")), set()).add(row.get("age_group"))
    lab_name = {attr: shown for _, attr, shown in LAB}
    lab_name["체크리스트"] = ""
    items, errors = [], []
    for row in rows:
        try:
            facts = facts_of(row)
        except SourceError as error:
            errors.append(f"{row.drug_id}: {error}")
            continue
        for gate, lab, answer, scoring, source in facts:
            name = drug_name(row, multi_route, siblings)
            template = "E-시점없음" if gate == "E" and "시점" not in scoring else ("G7-체크리스트" if lab == "체크리스트" else gate)
            question = QUESTION[template].format(약=name, 검사=lab_name.get(lab, ""))
            if gate == "G7" and lab != "체크리스트" and isinstance(answer, list) and len(answer) == 1:
                answer = answer[0]  # 금기가 하나뿐이면 단답 (목록 채점의 '정답에 없는 항목 → 틀림' 위험을 피함)
            items.append(
                {
                    "id": f"A-{row.drug_id}-{gate}" + (f"-{lab}" if lab and lab != "체크리스트" else ""),
                    "type": "A",
                    "gate": gate,
                    "기준": GATE_NAME[gate] + (f"({lab_name[lab]})" if lab_name.get(lab) else ("(체크리스트)" if lab == "체크리스트" else "")),
                    "drug_id": row.drug_id,
                    "drug_class": row.get("drug_class"),
                    "drug_name": name,
                    "question": question,
                    "answer": {"정답": answer, "채점": scoring, "형식": "목록" if isinstance(answer, list) else "단답"},
                    "원문": source,
                    "source_page": row.get("source_page"),
                    "짝키": f"{row.drug_id}|{gate}" + (f"|{lab}" if lab and lab != "체크리스트" else ""),
                }
            )
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        errors.append("문항 id 중복")
    return items, errors


# ---------------------------------------------------------------- 자체 시험: 원문 대조가 오류를 잡는가


def _answer(items: list[dict], item_id: str):
    return next((item["answer"]["정답"] for item in items if item["id"] == item_id), None)


def self_test(rows: list[Row]) -> tuple[list[str], list[str], int]:
    """CSV를 일부러 바꿔서, 정답이 바뀐 원문을 그대로 따르거나 멈추는지 본다.

    (실패 목록, 시험 불가 목록). 바꿀 대상 문자열이 지금 CSV에 없으면 '시험 불가'로 따로 알린다
    (CSV를 정당하게 고쳤는데 시험 때문에 생성이 막히지 않게).
    """

    def mutate(drug_id: str, column: str, change):
        changed = copy.deepcopy(rows)
        hit = False
        for row in changed:
            if row.drug_id == drug_id:
                before = row.data.get(column) or ""
                row.data[column] = change(before)
                hit = row.data[column] != before
        return changed if hit else None

    def sub(old: str, new: str):
        return lambda s: s.replace(old, new)

    stop = ("stop", None, None)
    cases = [
        # 이름, 바꾼 CSV, 기대: stop(멈춤) 또는 ("answer", 문항 id, 정답에 들어 있어야 할 말)
        ("CDAI ≥ → >", mutate("ADA-CD-adult", "activity_threshold", sub("CDAI ≥ 220", "CDAI > 220")), ("answer", "A-ADA-CD-adult-G3", "220 초과")),
        ("CDAI 값 변경", mutate("ADA-CD-adult", "activity_threshold", sub("CDAI ≥ 220", "CDAI ≥ 150")), ("answer", "A-ADA-CD-adult-G3", "150 이상")),
        ("CDAI 두 값", mutate("ADA-CD-adult", "activity_threshold", lambda s: s + " CDAI ≥ 150"), stop),
        ("CDAI 지움", mutate("ADA-CD-adult", "activity_threshold", sub("CDAI ≥ 220", "")), stop),
        ("activity_scale 비움", mutate("ADA-CD-adult", "activity_scale", lambda s: ""), stop),
        ("PUCAI 초과 → 이상", mutate("IFX-IV-UC-ped", "activity_threshold", sub("45 초과", "45 이상")), ("answer", "A-IFX-IV-UC-ped-G3", "45 이상")),
        ("내시경 조건 지움", mutate("ADA-UC", "activity_threshold", sub(" and Endoscopy subscore ≥ 2", "")), stop),
        ("Mayo and → or", mutate("ADA-UC", "activity_threshold", sub(" and Endoscopy", " or Endoscopy")), stop),
        ("직장출혈 조항 지움", mutate("ADA-UC", "eval_criteria", lambda s: re.split(r"\s*나\)", s)[0]), stop),
        ("유지 Mayo 하고 → 하거나", mutate("ADA-UC", "eval_criteria", sub("감소하고", "감소하거나")), stop),
        ("직장출혈 1점 → 2점", mutate("ADA-UC", "eval_criteria", sub("subscore 1점 이상", "subscore 2점 이상")), stop),
        ("유지 70점 → 100점", mutate("ADA-CD-adult", "eval_criteria", sub("70점", "100점")), stop),
        ("유지 또는 → 그리고", mutate("ADA-CD-adult", "eval_criteria", sub("감소 또는", "감소 그리고")), stop),
        ("평가 시점 불일치", mutate("ADA-CD-adult", "eval_criteria", sub("4주", "8주")), stop),
        ("Hb 값 두 개", mutate("TOF-UC", "lab_hb_min", lambda s: "※ FIL·UPA는 8 g/dL, TOF만 9 g/dL (미만 시 투여 불가)"), stop),
        ("Hb 숫자 지움", mutate("TOF-UC", "lab_hb_min", lambda s: "g/dL 미만 시 투여 불가"), stop),
        ("Hb 미만 → 이하", mutate("TOF-UC", "lab_hb_min", sub("미만 시", "이하 시")), ("answer", "A-TOF-UC-G6-hb", "초과")),
        ("금기 추가 (체크리스트 없는 행)", mutate("MTX-IBD", "contra_active_tb", lambda s: "Y"), ("answer", "A-MTX-IBD-G7", "활동성 결핵")),
        ("심전도 금기 내용 지움", mutate("OZA-UC", "ecg_required", lambda s: "Y"), stop),
        ("금기 칸 Y인데 체크리스트에 없음", mutate("TOF-UC", "contra_mao_inhibitor", lambda s: "Y"), stop),
        ("나이 칸 변경", mutate("BAL-UC-PED", "age_max", lambda s: "18"), stop),
        ("고령 조항 내용 변경", mutate("FIL-UC", "prior_bio_note", lambda s: "65세 이상 환자는 용량 감량에 한하여 사용"), stop),
        ("고령 조항 판정 칸 비움", mutate("UPA-CD", "prior_biologic", lambda s: "N"), stop),
        ("2가지가 구절 밖", mutate("ADA-UC", "activity_threshold", lambda s: "2가지 이상 " + s), stop),
        ("prior_bio_note 2가지 → 3가지", mutate("ADA-CD-adult", "prior_bio_note", sub("2가지", "3가지")), stop),
        ("보편적 치료 판정 칸 비움", mutate("ADA-CD-adult", "prior_conventional", lambda s: ""), stop),
        ("완전장관영양법 유지", rows, ("answer", "A-IFX-IV-CD-ped-G4", "완전장관영양법")),
        ("ADA 베체트 나이 생김", mutate("ADA-GIBD", "age_min", lambda s: "19"), stop),
        ("체크리스트에 CSV 메모 없음", rows, ("absent", "A-TOF-UC-G7", "★")),
        ("※ 문구는 체크리스트 항목 아님", rows, ("absent", "A-UPA-CD-G7", "면역조절제")),
        ("괄호 밖 CSV 메모", mutate("UPA-UC", "notes", sub("활동성 결핵 없음", "활동성 결핵 없음 ★확인 필요")), stop),
        ("누공 소제목은 정답 아님", rows, ("absent", "A-IFX-IV-CD-adult-G3", "누공")),
        ("대조 정답 표현 통일", rows, ("answer", "A-IFX-SC-CD-fistula-G3", "가이드북에 적혀 있지 않다")),
    ]
    failures, skipped = [], []
    for name, changed, (kind, item_id, expected) in cases:
        if changed is None:
            skipped.append(name)
            continue
        items, errors = build(changed)
        if kind == "stop" and not errors:
            failures.append(f"자체 시험 '{name}': 멈춰야 하는데 통과함")
        if kind == "absent":
            value = _answer(items, item_id)
            text = " / ".join(value) if isinstance(value, list) else str(value)
            if errors or expected in text:
                failures.append(f"자체 시험 '{name}': {item_id} 정답 {text!r}에 '{expected}'가 들어 있음 {errors[:1]}")
        if kind == "answer":
            value = _answer(items, item_id)
            text = " / ".join(value) if isinstance(value, list) else str(value)
            if errors or expected not in text:
                failures.append(f"자체 시험 '{name}': {item_id} 정답 {text!r}에 '{expected}' 없음 {errors[:1]}")
    return failures, skipped, len(cases)


# ---------------------------------------------------------------- 출력


def write_review(path: Path, items: list[dict]) -> None:
    columns = ["id", "기준", "약", "질문", "정답", "채점 열쇠", "원문", "근거쪽", "판정", "수정 정답", "검수자", "코멘트"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in items:
            value = item["answer"]["정답"]
            writer.writerow(
                {
                    "id": item["id"],
                    "기준": item["기준"],
                    "약": item["drug_name"],
                    "질문": item["question"],
                    "정답": " / ".join(value) if isinstance(value, list) else value,
                    "채점 열쇠": json.dumps(item["answer"]["채점"], ensure_ascii=False),
                    "원문": item["원문"],
                    "근거쪽": item["source_page"],
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="STAGE1 A형: 급여 기준 서술형 문항")
    parser.add_argument("--csv", help=f"가이드북 CSV. 기본값 {DEFAULT_CSV}")
    args = parser.parse_args()
    csv_path = Path(args.csv) if args.csv else DEFAULT_CSV
    if not csv_path.exists():
        print(f"CSV가 없다: {csv_path}\n--csv 로 경로를 준다.")
        return 1
    rows, digest = load_rows(csv_path)
    failures, skipped, total = self_test(rows)
    if skipped:
        print(f"자체 시험 {len(skipped)}건은 바꿀 문자열이 지금 CSV에 없어 건너뜀: {', '.join(skipped)}")
    if failures:
        print("\n".join(failures))
        print("원문 대조가 오류를 제대로 잡지 못한다 — 문항을 쓰지 않았다")
        return 1
    items, errors = build(rows)
    if errors:
        print("\n".join(errors[:50]))
        print(f"원문에서 기준을 하나로 읽지 못함 {len(errors)}건 — 문항을 쓰지 않았다")
        return 1
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "a_items.jsonl").open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    write_review(OUTPUT / "a_review.csv", items)
    unique = {json.dumps(item["answer"]["정답"], ensure_ascii=False) for item in items}
    summary = {
        "csv": str(csv_path),
        "csv_sha256": digest,
        "행": len(rows),
        "문항수": len(items),
        "고유 정답 수": len(unique),
        "기준별": dict(Counter(item["기준"].split("(")[0] for item in items)),
        "형식별": dict(Counter(item["answer"]["형식"] for item in items)),
        "약계열별": dict(Counter(item["drug_class"] for item in items)),
        "자체 시험": {"통과": total - len(skipped), "건너뜀": skipped},
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"자체 시험 통과 (일부러 바꾼 CSV {total - len(skipped)}건 모두 멈추거나 바뀐 원문을 따름)")
    print(f"A형 {len(items)}문항 (고유 정답 {len(unique)}개) → {OUTPUT / 'a_items.jsonl'}")
    print(f"검수 양식 → {OUTPUT / 'a_review.csv'}")
    print(json.dumps(summary["기준별"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
