"""IBD보험가이드북.csv 한 행을 RAG 청크 하나로 바꾼다 (API 없음, 2026-11-18).

목적: 가이드북 PDF 쪽 대신 CSV 행을 검색 대상으로 쓰는 'CSV-RAG' 조건을 만든다.
      결과 파일은 IBD_insurance_guide_2024.jsonl과 같은 모양이라 백엔드 검색(BM25·임베딩·RRF·리랭커)과
      답 생성 프롬프트를 그대로 쓴다. 바뀌는 것은 검색 대상뿐이다.

청크 규칙
  - 44행 → 44청크. id는 drug_id.
  - 본문은 '열 이름표: 값' 한 줄씩. 빈칸은 뺀다. 값은 CSV 그대로 (N·Y도 바꾸지 않음).
  - source_chunks(내부 색인 번호)만 뺀다. notes·adverse_effects 등 나머지 칸은 모두 넣는다.
  - 제목에 약 이름·질환·연령군을 한글로 풀어 써서 BM25가 약 이름과 질환으로도 찾게 한다.
  - page는 source_page의 첫 쪽 번호 (답 생성 프롬프트의 'p.N' 표시용).

실행:
    python3 make_csv_corpus.py            # → IBD_insurance_csv_2024.jsonl
    python3 Embedding.py --source IBD_insurance_csv_2024.jsonl --output IBD_insurance_csv_2024.embeddings.jsonl  (API)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE.parent / "IBD보험가이드북.csv"
OUTPUT = HERE / "IBD_insurance_csv_2024.jsonl"
SOURCE_TITLE = "2024 대한장연구학회 염증성장질환 보험가이드북 Ver.3 (CSV 정리본)"

DISEASE = {"CD": "크론병", "UC": "궤양성 대장염", "GIBD": "장형 베체트", "CD/UC": "크론병·궤양성 대장염"}
AGE_GROUP = {"adult": "성인", "pediatric": "소아"}

# 본문에 넣는 순서와 이름표. 여기에 없는 열이 CSV에 생기면 멈춘다.
LABELS = {
    "drug_id": "행 ID",
    "drug_en": "성분명(영문)",
    "drug_kr": "제품명",
    "drug_class": "약 계열",
    "mechanism": "기전",
    "route": "투여 경로",
    "disease": "질환",
    "age_group": "연령군",
    "age_min": "최소 나이",
    "age_max": "최대 나이",
    "activity_scale": "활성도 척도",
    "activity_threshold": "활성도 기준",
    "prior_conventional": "이전 보편적 치료 조건",
    "prior_biologic": "이전 생물학제제 조건",
    "prior_bio_note": "이전 치료 메모",
    "is_jak": "JAK 억제제",
    "jak_age_restriction": "JAK 고령 제한",
    "jak_cv_restriction": "JAK 심혈관 위험 제한",
    "jak_malignancy_restriction": "JAK 악성종양 위험 제한",
    "eval_week": "유지 평가 시점",
    "eval_criteria": "유지 평가 기준",
    "induction_dose": "유도 용량",
    "maintenance_dose": "유지 용량",
    "elderly_dose": "고령 용량",
    "tb_screening": "결핵 검사",
    "ecg_required": "심전도 필요",
    "vzv_check": "대상포진(VZV) 확인",
    "pregnancy_contra": "임신 금기",
    "lab_anc_min": "ANC 하한",
    "lab_alc_min": "ALC 하한",
    "lab_hb_min": "Hb 하한",
    "contra_active_infection": "금기: 활동성 감염",
    "contra_active_tb": "금기: 활동성 결핵",
    "contra_severe_hepatic": "금기: 중증 간장애",
    "contra_severe_renal": "금기: 중증 신장애",
    "contra_recent_cv_event": "금기: 최근 심혈관 사건",
    "contra_mao_inhibitor": "금기: MAO 억제제",
    "contra_immunomodulator": "금기: 면역조절제 병용",
    "self_injection": "자가주사",
    "extended_rx_24wk": "24주 장기처방",
    "switch_target_for": "교체투여 대상",
    "source_page": "가이드북 쪽",
    "adverse_effects": "이상반응",
    "notes": "메모",
}
SKIP = {"source_chunks"}


def disease_names(code: str) -> list[str]:
    return [DISEASE.get(part.strip(), part.strip()) for part in code.split("/") if part.strip()]


def first_page(value: str) -> int | None:
    found = re.search(r"p\.?\s*(\d+)", value)
    return int(found.group(1)) if found else None


def build(rows: list[dict]) -> list[dict]:
    columns = set(rows[0])
    unknown = columns - set(LABELS) - SKIP
    if unknown:
        raise SystemExit(f"이름표가 없는 열: {sorted(unknown)} (LABELS에 추가하세요)")
    ids = [row["drug_id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit("drug_id가 겹칩니다.")

    records = []
    for row in rows:
        diseases = disease_names(row["disease"])
        names = [n for n in (row["drug_en"].strip(), row["drug_kr"].strip()) if n]
        age = AGE_GROUP.get(row["age_group"].strip(), row["age_group"].strip())
        title = " · ".join(filter(None, [" / ".join(names), "·".join(diseases), age]))
        lines = [f"{label}: {row[col].strip()}" for col, label in LABELS.items() if row.get(col, "").strip()]
        text = f"[{SOURCE_TITLE} · {row['drug_id']} · {title}]\n" + "\n".join(lines)
        records.append({
            "id": f"CSV-{row['drug_id']}",
            "source": "IBD보험가이드북.csv",
            "source_title": SOURCE_TITLE,
            "language": "ko",
            "page": first_page(row["source_page"]),
            "section": row["drug_class"].strip(),
            "title": title,
            "drugs": names,
            "disease": diseases,
            "text": text,
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    raw = args.csv.read_bytes()
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    records = build(rows)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    lengths = sorted(len(r["text"]) for r in records)
    print(f"{len(records)}청크 → {args.output}")
    print(f"글자 수: 최소 {lengths[0]}, 중간 {lengths[len(lengths) // 2]}, 최대 {lengths[-1]}")
    print(f"CSV sha256: {hashlib.sha256(raw).hexdigest()[:16]}")


if __name__ == "__main__":
    main()
