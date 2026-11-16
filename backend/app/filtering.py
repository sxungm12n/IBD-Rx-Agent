"""급여 후보를 사용 가능 / 보류 / 제외로 나눈다.

- 사용 가능: 입력한 조건을 모두 통과했고, 확인할 것이 남지 않은 약
- 보류: 제외 사유는 없지만 확인할 것(미입력 값, 투여 전 요건)이 남은 약
- 제외: 원문 기준에 맞지 않는 약. 해당하는 사유를 모두 안전 → 자격 → 활성도 순으로 남긴다.

화면에서 아예 빼는 행 (어느 목록에도 넣지 않는다)
- 질환이 다른 약
- 누공성 행인데 누공성 체크가 꺼진 경우
- 나이가 맞지 않고, 같은 약·같은 투여경로의 다른 연령 행은 나이가 맞는 경우
  (예: 40세 UC 환자에게 Mesalamine 소아 행)
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/eligibility", tags=["eligibility"])

PEDIATRIC_BELOW = 19
CONVENTIONAL_TOOLTIP = {
    "CD": "2가지 이상",
    "UC": "스테로이드·6-MP·AZA",
    "GIBD": "5-ASA 포함 2가지 이상",
}

GROUP_AVAILABLE = "사용 가능"
GROUP_HOLD = "보류"
GROUP_EXCLUDED = "제외"

# (입력 필드, CSV 열, 화면 문구). 임신 가능성·수유는 CSV에 전용 열이 없어 원문 문구로 판정한다.
CHECKBOXES = (
    ("active_infection", "contra_active_infection", "활성 감염"),
    ("active_tb", "contra_active_tb", "활동성 결핵"),
    ("severe_hepatic", "contra_severe_hepatic", "중증 간장애(Child-Pugh C)"),
    ("severe_renal", "contra_severe_renal", "말기 신부전(CrCl <15)"),
    ("pregnant", "pregnancy_contra", "임신"),
    ("pregnancy_potential", None, "임신 가능성"),
    ("lactation", None, "수유"),
    ("recent_cv_event", "contra_recent_cv_event", "최근 6개월 심혈관 사건"),
    ("mao_inhibitor", "contra_mao_inhibitor", "MAO 억제제 복용"),
    ("immunomodulator", "contra_immunomodulator", "면역조절제 병용"),
    ("ecg_contraindication", "ecg_required", "ECG 금기 소견"),
)
SAFETY_FIELDS = tuple(field for field, _, _ in CHECKBOXES) + ("cv_risk", "malignancy_risk")

DISEASE_LABEL = {
    "CD": "크론병",
    "UC": "궤양성 대장염",
    "GIBD": "장형 베체트병",
}


class CaseInput(BaseModel):
    disease: str = Field(description="CD, UC, GIBD 또는 한글 질환명")
    age: int = Field(ge=0, le=120, description="만 나이")
    fistula: bool = False
    conventional_failure: bool = False
    biologic_failure: bool = Field(default=False, description="생물학제제 실패·불내성")
    cdai: float | None = None
    pcdai: float | None = None
    mayo: float | None = None
    endoscopy_subscore: float | None = None
    pucai: float | None = None
    intestinal_ulcer: str | None = Field(default=None, description="있음, 없음, 또는 비움")
    active_infection: bool = False
    active_tb: bool = False
    severe_hepatic: bool = False
    severe_renal: bool = False
    pregnant: bool = False
    pregnancy_potential: bool = False
    lactation: bool = False
    cv_risk: bool = False
    malignancy_risk: bool = False
    recent_cv_event: bool = False
    mao_inhibitor: bool = False
    immunomodulator: bool = False
    ecg_contraindication: bool = False
    vzv_confirmed: bool = Field(default=False, description="수두 병력·접종 문서 또는 VZV 항체 확인됨")
    anc: float | None = Field(default=None, description="cells/mm³")
    alc: float | None = Field(default=None, description="cells/mm³")
    hb: float | None = Field(default=None, description="g/dL")


@dataclass(frozen=True)
class Drug:
    data: dict[str, str]

    def get(self, key: str) -> str:
        return self.data.get(key, "").strip()

    @property
    def drug_id(self) -> str:
        return self.get("drug_id")

    def yes(self, key: str) -> bool:
        return self.get(key).startswith("Y")

    def diseases(self) -> set[str]:
        return {part for part in self.get("disease").split("/") if part}

    def sibling_key(self) -> tuple[str, str, str]:
        """연령만 다른 같은 약 행을 묶는 키."""
        return (self.get("drug_en"), self.get("route"), self.get("disease"))

    def pregnancy_text(self) -> str:
        return (self.get("pregnancy_contra") + " " + self.get("notes")).replace(" ", "")

    def contra_pregnancy_potential(self) -> bool:
        # 원문: FIL·TOF·UPA "임신가능성 여성", OZA "임신가능성 없는 여성". MTX는 임부만.
        return self.yes("pregnancy_contra") and "임신가능성" in self.pregnancy_text()

    def contra_lactation(self) -> bool:
        # 원문: FIL·UPA만 "수유부".
        return self.yes("pregnancy_contra") and "수유" in self.pregnancy_text()

    def weight_minimum(self) -> float | None:
        found = re.search(r"체중\s*(\d+(?:\.\d+)?)\s*kg\s*초과", self.get("activity_threshold"))
        return float(found.group(1)) if found else None


def guidebook_path() -> Path:
    override = os.environ.get("GUIDEBOOK_CSV")
    if override:
        return Path(override)
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "IBD보험가이드북.csv"


_CACHE: tuple[str, float, tuple[Drug, ...]] | None = None


def load_drugs() -> tuple[Drug, ...]:
    global _CACHE
    path = guidebook_path()
    if not path.is_file():
        raise FileNotFoundError(f"가이드북 CSV를 찾을 수 없습니다: {path}")
    stamp = path.stat().st_mtime
    if _CACHE and _CACHE[0] == str(path) and _CACHE[1] == stamp:
        return _CACHE[2]
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    drugs = tuple(Drug({key.strip(): (value or "") for key, value in row.items()}) for row in rows)
    _CACHE = (str(path), stamp, drugs)
    return drugs


def normalize_disease(value: str) -> str:
    text = value.strip()
    aliases = {
        "CD": "CD",
        "크론병": "CD",
        "UC": "UC",
        "궤양성 대장염": "UC",
        "GIBD": "GIBD",
        "장형 베체트": "GIBD",
        "장형 베체트병": "GIBD",
    }
    if text not in aliases:
        raise HTTPException(status_code=422, detail="질환은 크론병, 궤양성 대장염, 장형 베체트병 중 하나여야 합니다.")
    return aliases[text]


def normalize_ulcer(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    text = value.strip()
    if text in {"있음", "present", "yes"}:
        return "있음"
    if text in {"없음", "absent", "no"}:
        return "없음"
    raise HTTPException(status_code=422, detail="장 궤양은 있음, 없음, 또는 비움이어야 합니다.")


def _number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _cutoff(text: str) -> float | None:
    """검사 기준값을 cells/mm³ 또는 g/dL로 읽는다. ×10⁹/L는 1000을 곱한다."""
    if not text:
        return None
    hb = re.search(r"(\d+(?:\.\d+)?)\s*g/dL", text, flags=re.I)
    if hb:
        return float(hb.group(1))
    sci = re.search(r"(\d+(?:\.\d+)?)\s*[×x]\s*10", text)
    if sci:
        return float(sci.group(1)) * 1000
    plain = re.search(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)", text)
    if not plain:
        return None
    return float(plain.group(1).replace(",", ""))


def _optional_int(text: str) -> int | None:
    if not text.strip():
        return None
    return int(text)


# ---------------------------------------------------------------- 판정 단계


def _age_reasons(drug: Drug, case: CaseInput) -> list[str]:
    low = _optional_int(drug.get("age_min"))
    high = _optional_int(drug.get("age_max"))
    if low is not None and case.age < low:
        return [f"나이 {case.age}세 — {low}세 이상만 급여"]
    if high is not None and case.age > high:
        return [f"나이 {case.age}세 — {high}세 이하만 급여"]
    return []


def _safety_reasons(drug: Drug, case: CaseInput) -> list[str]:
    reasons = []
    for field, column, label in CHECKBOXES:
        if not getattr(case, field):
            continue
        if field == "pregnancy_potential":
            matched = drug.contra_pregnancy_potential()
        elif field == "lactation":
            matched = drug.contra_lactation()
        else:
            matched = drug.yes(column)
        if matched:
            reasons.append(f"금기: {label}")
    return reasons


def _lab(drug: Drug, case: CaseInput) -> tuple[list[str], list[str]]:
    reasons, checks = [], []
    for key, value, label, unit in (
        ("lab_anc_min", case.anc, "ANC", "cells/mm³"),
        ("lab_alc_min", case.alc, "ALC", "cells/mm³"),
        ("lab_hb_min", case.hb, "Hb", "g/dL"),
    ):
        minimum = _cutoff(drug.get(key))
        if minimum is None:
            continue
        if value is None:
            checks.append(f"{label} 미입력 — {_number(minimum)} {unit} 이상 필요")
        elif value < minimum:
            reasons.append(f"{label} {_number(value)} — {_number(minimum)} {unit} 이상 필요")
    return reasons, checks


def _eligibility_reasons(drug: Drug, case: CaseInput) -> list[str]:
    reasons = []
    if drug.get("prior_conventional") == "Y" and not case.conventional_failure:
        reasons.append("보편적 치료 실패·불내성·금기 이력 없음")

    if drug.get("prior_biologic") == "conditional" and not case.biologic_failure:
        risks = []
        if case.age >= 65:
            risks.append("65세 이상")
        if case.cv_risk:
            risks.append("심혈관 고위험")
        if case.malignancy_risk:
            risks.append("악성종양 위험")
        if risks:
            reasons.append(f"{'·'.join(risks)} — 생물학제제 실패·불내성 후에만 급여")
    return reasons


def _activity(drug: Drug, case: CaseInput) -> tuple[list[str], list[str]]:
    """(제외 사유, 확인할 것). 둘 다 비면 활성도 기준이 없는 약이다."""
    scale = drug.get("activity_scale")
    text = drug.get("activity_threshold")
    reasons: list[str] = []
    checks: list[str] = []

    if scale == "DAIBD" or "장 궤양" in text:
        if case.intestinal_ulcer is None:
            checks.append("내시경상 장 궤양 미입력")
        elif case.intestinal_ulcer == "없음":
            reasons.append("내시경상 장 궤양 없음 — 궤양 확인 필요")
        return reasons, checks

    if scale == "CDAI":
        if case.cdai is None:
            checks.append("CDAI 미입력 — 220 이상 필요")
        else:
            found = re.search(r"(?<!P)CDAI\s*≥\s*(\d+)", text)
            minimum = float(found.group(1)) if found else 220.0
            if case.cdai < minimum:
                reasons.append(f"CDAI {_number(case.cdai)} — {_number(minimum)} 이상 필요")
        return reasons, checks

    if scale == "PCDAI":
        if case.pcdai is None:
            checks.append("PCDAI 미입력 — 30 이상 필요")
        else:
            found = re.search(r"PCDAI\s*≥\s*(\d+(?:\.\d+)?)", text)
            minimum = float(found.group(1)) if found else 30.0
            if case.pcdai < minimum:
                reasons.append(f"PCDAI {_number(case.pcdai)} — {_number(minimum)} 이상 필요")
        return reasons, checks

    if scale == "PUCAI":
        if case.pucai is None:
            checks.append("PUCAI 미입력 — 45 초과 필요")
        elif case.pucai <= 45:
            reasons.append(f"PUCAI {_number(case.pucai)} — 45 초과 필요")
        return reasons, checks

    if scale == "Mayo+Endo":
        if case.mayo is None:
            checks.append("Mayo 미입력 — 6~12 필요")
        elif not 6 <= case.mayo <= 12:
            reasons.append(f"Mayo {_number(case.mayo)} — 6~12 필요")
        if case.endoscopy_subscore is None:
            checks.append("내시경 Subscore 미입력 — 2 이상 필요")
        elif case.endoscopy_subscore < 2:
            reasons.append(f"내시경 Subscore {_number(case.endoscopy_subscore)} — 2 이상 필요")
        return reasons, checks

    return reasons, checks


def _pre_dose(drug: Drug, case: CaseInput) -> tuple[list[str], list[str]]:
    """(보류로 보내는 확인할 것, 상태에 영향 없는 투여 전 안내)."""
    checks, notes = [], []
    if drug.yes("tb_screening"):
        if case.active_tb:
            checks.append("활동성 결핵 체크됨 — 결핵 치료 후 투여 여부 판단")
        else:
            notes.append("투여 전 결핵 선별검사")
    if drug.yes("vzv_check") and not case.vzv_confirmed:
        checks.append("VZV 확인 필요 — 수두 병력·접종 문서 없으면 항체 검사")
    weight = drug.weight_minimum()
    if weight is not None:
        checks.append(f"체중 {_number(weight)}kg 초과 확인")
    return checks, notes


TARGET_LABEL = {"adult": "성인", "pediatric": "소아", "fistulizing": "누공성"}


def _card(drug: Drug, **extra) -> dict:
    return {
        "drug_id": drug.drug_id,
        "name": drug.get("drug_en") or drug.drug_id,
        "product": drug.get("drug_kr"),
        "route": drug.get("route"),
        # 같은 약이 성인·소아·누공성 행으로 나뉘어 있어 화면에서 구분이 필요하다.
        "target": TARGET_LABEL.get(drug.get("age_group")),
        "drug_class": drug.get("drug_class"),
        "source_page": drug.get("source_page"),
        **extra,
    }


def judge_drug(drug: Drug, case: CaseInput, disease: str) -> dict | None:
    """카드 하나. 화면에서 뺄 행이면 None."""
    if disease not in drug.diseases():
        return None
    if drug.get("age_group") == "fistulizing" and not (disease == "CD" and case.fistula):
        return None

    age_reasons = _age_reasons(drug, case)
    lab_reasons, lab_checks = _lab(drug, case)
    activity_reasons, activity_checks = _activity(drug, case)
    pre_checks, notes = _pre_dose(drug, case)

    # 안전 → 나이 → 자격 → 활성도 순서. 화면에서는 위에 있는 사유가 먼저 보인다.
    reasons = (
        _safety_reasons(drug, case)
        + lab_reasons
        + age_reasons
        + _eligibility_reasons(drug, case)
        + activity_reasons
    )
    checks = pre_checks + lab_checks + activity_checks

    if reasons:
        return {"group": GROUP_EXCLUDED, "_age_fail": bool(age_reasons), **_card(drug, reasons=reasons)}
    if checks:
        return {"group": GROUP_HOLD, **_card(drug, checks=checks, notes=notes)}
    return {"group": GROUP_AVAILABLE, **_card(drug, notes=notes)}


def _notices(case: CaseInput) -> list[str]:
    notices = []
    safety_entered = any(getattr(case, field) for field in SAFETY_FIELDS)
    labs_entered = any(value is not None for value in (case.anc, case.alc, case.hb))
    if not safety_entered and not labs_entered:
        notices.append("안전성·금기를 입력하지 않았습니다. 금기가 없다고 보고 판정했습니다.")
    if safety_entered:
        notices.append("체크한 금기는 원문에 그 금기가 적힌 약만 제외합니다. 나머지 약은 허가사항을 확인하세요.")
    return notices


def evaluate(case: CaseInput) -> dict:
    disease = normalize_disease(case.disease)
    case = case.model_copy(update={"intestinal_ulcer": normalize_ulcer(case.intestinal_ulcer)})

    cards = [card for drug in load_drugs() if (card := judge_drug(drug, case, disease)) is not None]
    drugs = {drug.drug_id: drug for drug in load_drugs()}

    # 나이가 안 맞는 행은, 같은 약·같은 경로의 다른 연령 행이 나이를 통과하면 뺀다.
    age_ok = {
        drugs[card["drug_id"]].sibling_key()
        for card in cards
        if not card.get("_age_fail")
    }
    groups: dict[str, list[dict]] = {GROUP_AVAILABLE: [], GROUP_HOLD: [], GROUP_EXCLUDED: []}
    for card in cards:
        if card.pop("_age_fail", False) and drugs[card["drug_id"]].sibling_key() in age_ok:
            continue
        groups[card.pop("group")].append(card)

    groups[GROUP_HOLD].sort(key=lambda card: len(card["checks"]))

    pediatric = case.age < PEDIATRIC_BELOW
    return {
        "patient": f"{DISEASE_LABEL[disease]} · {case.age}세({'소아' if pediatric else '성인'})",
        "summary": {name: len(items) for name, items in groups.items()},
        "notices": _notices(case),
        GROUP_AVAILABLE: groups[GROUP_AVAILABLE],
        GROUP_HOLD: groups[GROUP_HOLD],
        GROUP_EXCLUDED: groups[GROUP_EXCLUDED],
    }


def render_text(result: dict) -> str:
    """로그·시연용 텍스트. 화면은 JSON을 그대로 쓴다."""
    lines = [result["patient"]]
    lines.append(" · ".join(f"{name} {count}" for name, count in result["summary"].items()))
    lines.extend(f"※ {notice}" for notice in result["notices"])

    def head(card: dict) -> str:
        parts = [card["name"], card["route"]]
        if card["target"]:
            parts.append(card["target"])
        text = " · ".join(parts)
        if card["product"]:
            text += f" — {card['product']}"
        return f"{text}  [{card['source_page']}]"

    lines.append(f"\n■ {GROUP_AVAILABLE}")
    for card in result[GROUP_AVAILABLE]:
        lines.append(f"  ✓ {head(card)}")
        lines.extend(f"      · {note}" for note in card["notes"])
    lines.append(f"\n■ {GROUP_HOLD} (확인할 것)")
    for card in result[GROUP_HOLD]:
        lines.append(f"  ? {head(card)}")
        lines.extend(f"      - {check}" for check in card["checks"])
        lines.extend(f"      · {note}" for note in card["notes"])
    lines.append(f"\n■ {GROUP_EXCLUDED} (사유)")
    for card in result[GROUP_EXCLUDED]:
        lines.append(f"  ✕ {head(card)}")
        lines.extend(f"      - {reason}" for reason in card["reasons"])
    return "\n".join(lines)


# ---------------------------------------------------------------- API


def form_spec() -> dict:
    return {
        "diseases": [
            {"value": "CD", "label": "크론병", "fistula": True},
            {"value": "UC", "label": "궤양성 대장염", "fistula": False},
            {"value": "GIBD", "label": "장형 베체트병", "fistula": False},
        ],
        "pediatric_below": PEDIATRIC_BELOW,
        "conventional_tooltip": CONVENTIONAL_TOOLTIP,
        "activity": {
            "CD": {"19세 이상": ["cdai"], "19세 미만": ["pcdai"]},
            "UC": {"19세 이상": ["mayo", "endoscopy_subscore"], "19세 미만": ["pucai"]},
            "GIBD": {"19세 이상": ["intestinal_ulcer"], "19세 미만": ["intestinal_ulcer"]},
        },
        "ulcer_values": ["있음", "없음"],
        "checks": [{"key": field, "label": label} for field, _, label in CHECKBOXES]
        + [
            {"key": "cv_risk", "label": "심혈관 고위험"},
            {"key": "malignancy_risk", "label": "악성종양 위험"},
            {"key": "vzv_confirmed", "label": "VZV 항체 확인됨"},
        ],
        "labs": [
            {"key": "anc", "label": "ANC", "unit": "cells/mm³"},
            {"key": "alc", "label": "ALC", "unit": "cells/mm³"},
            {"key": "hb", "label": "Hb", "unit": "g/dL"},
        ],
        "groups": [GROUP_AVAILABLE, GROUP_HOLD, GROUP_EXCLUDED],
    }


@router.get("/form")
def get_form() -> dict:
    return form_spec()


@router.post("")
def post_eligibility(case: CaseInput) -> dict:
    try:
        return evaluate(case)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
