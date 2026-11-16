"""CSV 원문 대조 검수표 (2026-11-11). 문항(A·A2·C형)이 쓰는 CSV 칸만 골라 임상의가 PDF와 대조하게 한다. API 없음.
사용: python3 make_csv_review.py <STAGE1 dir> <guide.pdf> <out.xlsx>   (openpyxl, pypdf 필요)
"""
import csv, io, json, re, sys
from collections import defaultdict
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from pypdf import PdfReader

ST, PDF, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3])
CSV_PATH = ST.parents[2] / "data" / "IBD보험가이드북.csv"
rows = [{k.strip(): (v or "") for k, v in r.items()} for r in csv.DictReader(io.StringIO(CSV_PATH.read_bytes().decode("utf-8-sig")))]

def load(name):
    p = ST / "output" / name
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
items = load("a_items.jsonl") + load("a2_items.jsonl") + load("c_items.jsonl")

# 칸 → (한글 이름, 이 칸을 쓰는 문항 판별 함수)
GATE = lambda *gs: (lambda it: it["gate"] in gs)
C_GATE = lambda *gs: (lambda it: it.get("type") == "C" and it["gate"] in gs)
FIELDS = [
    ("age_min", "연령 하한", lambda it: (it["gate"] == "G2") or (it.get("type") == "C" and it["gate"] == "나이")),
    ("age_max", "연령 상한", GATE("G2")),
    ("activity_scale", "활성도 척도", lambda it: it["gate"] == "G3" or (it.get("type") == "C" and it["gate"] in ("활성도", "전체"))),
    ("activity_threshold", "활성도 기준 문장", lambda it: it["gate"] == "G3" or (it.get("type") == "C" and it["gate"] in ("활성도", "전체"))),
    ("prior_conventional", "보편적 치료 실패 필요(Y/N)", lambda it: it["gate"] == "G4" or (it.get("type") == "C" and it["gate"] in ("이전 치료", "전체"))),
    ("prior_biologic", "생물학제제 실패 필요 여부", lambda it: it["gate"] in ("G4", "G5") or (it.get("type") == "C" and it["gate"] in ("고령·고위험", "전체"))),
    ("prior_bio_note", "이전 치료·고령 조항 문장", lambda it: it["gate"] in ("G4", "G5") or (it.get("type") == "C" and it["gate"] in ("이전 치료", "고령·고위험", "전체"))),
    ("eval_week", "유지 평가 시점", lambda it: it["gate"] == "E" or (it.get("type") == "C" and it["gate"] == "유지 기준")),
    ("eval_criteria", "유지 인정 기준 문장", lambda it: it["gate"] == "E" or (it.get("type") == "C" and it["gate"] == "유지 기준")),
    ("lab_hb_min", "Hb 하한", lambda it: it["gate"] == "G6" and it["id"].endswith("-hb") or (it.get("type") == "C" and it["gate"] == "검사 하한" and "hb" in it["id"])),
    ("lab_anc_min", "ANC 하한", lambda it: it["gate"] == "G6" and it["id"].endswith("-anc") or (it.get("type") == "C" and it["id"].endswith("anc-low"))),
    ("lab_alc_min", "ALC 하한", lambda it: it["gate"] == "G6" and it["id"].endswith("-alc") or (it.get("type") == "C" and it["id"].endswith("alc-low"))),
    ("ecg_required", "심전도 금기", GATE("G7")),
    ("pregnancy_contra", "임신 금기", GATE("G7")),
    ("contra_active_infection", "활동성 감염 금기", GATE("G7")),
    ("contra_active_tb", "활동성 결핵 금기", GATE("G7")),
    ("contra_severe_hepatic", "중증 간장애 금기", GATE("G7")),
    ("contra_severe_renal", "중증 신장애 금기", GATE("G7")),
    ("contra_recent_cv_event", "최근 심혈관 사건 금기", GATE("G7")),
    ("contra_mao_inhibitor", "MAO 억제제 병용 금기", GATE("G7")),
    ("contra_immunomodulator", "면역조절제 병용 금기", GATE("G7")),
]
NOTE_TAGS = [("스위치", "교체투여(스위치)", "W"), ("장기처방", "장기 처방", "L"), ("장기처방(p.23)", "장기 처방(p.23)", "L"),
             ("장기처방(p.26)", "장기 처방(p.26)", "L"), ("처방(p.28)", "처방(p.28)", "L"), ("자가주사", "자가주사", "J"), ("증량", "용량 증량", "D"),
             ("평가", "유지 평가(메모)", "E"), ("원문 상이", "원문 상이 메모", "E")]
GENERAL = [("재투여(p.58)", "휴약 후 재투여", "R"), ("교체·처방(p.59)", "교체 투여·처방량", "P"),
           ("TDM(p.11)", "혈중농도 검사(TDM) 급여", "T"), ("항-Infliximab 항체검사(p.12)", "항체검사 급여", "T")]

def tag(notes, name):
    m = re.search(r"\[" + re.escape(name) + r"\]([^\[]*)", notes)
    return m.group(1).strip().rstrip("/").strip() if m else None

# PDF 위치 찾기: 값의 앞부분(공백 제거)이 들어 있는 장
pdf_pages = [re.sub(r"\s+", "", p.extract_text() or "") for p in PdfReader(str(PDF)).pages]
def sheets_of(book_pages: str) -> str:
    """책 쪽 → PDF 장 (PDF 1장 = 책 2쪽: 장 = 쪽//2 + 1. p.11→6, p.27→14, p.56→29, p.58·59→30에서 확인)"""
    nums = [int(n) for n in re.findall(r"p\.(\d+)", book_pages)]
    return ", ".join(str(x) for x in dict.fromkeys(n // 2 + 1 for n in nums))


def pdf_where(value, book_pages=""):
    found = pdf_find(value)
    conv = sheets_of(book_pages)
    return found if found else (conv + " (책 쪽 환산)" if conv else "책 쪽으로 확인")


def pdf_find(value):
    v = re.sub(r"\s+", "", value)
    v = re.sub(r"[★※].*", "", v)
    for n in (24, 16, 10):
        frag = v[:n]
        if len(frag) >= 6:
            hits = [i + 1 for i, t in enumerate(pdf_pages) if frag in t]
            if hits:
                return ", ".join(map(str, hits[:6])) + " (값 검색)"
    return ""

by_drug = defaultdict(list)
for it in items:
    by_drug[it["drug_id"]].append(it)

recs = []
for r in rows:
    did = r["drug_id"]
    its = by_drug.get(did, [])
    for col, label, use in FIELDS:
        val = r.get(col, "")
        if not val.strip() or val.strip() == "N" and col.startswith(("contra", "ecg", "pregnancy")):
            continue
        used = [it["id"] for it in its if use(it)]
        if not used:
            continue
        recs.append((did, r["drug_kr"], r["disease"], r["age_group"], label, col, val, r["source_page"], pdf_where(val, r["source_page"]), len(used), " ".join(used[:12]) + (" …" if len(used) > 12 else "")))
    for tg, label, gate in NOTE_TAGS:
        val = tag(r["notes"], tg)
        if not val:
            continue
        used = [it["id"] for it in its if (it.get("type") == "A2" and it["gate"] == gate) or (gate == "E" and (it["gate"] == "E" or it.get("type") == "C" and it["gate"] == "유지 기준"))]
        if not used:
            continue
        recs.append((did, r["drug_kr"], r["disease"], r["age_group"], label, "notes:" + tg, val[:500], r["source_page"], pdf_where(val, r["source_page"]), len(used), " ".join(used[:12]) + (" …" if len(used) > 12 else "")))
gen = []
for tg, label, gate in GENERAL:
    vals = {tag(r["notes"], tg) for r in rows} - {None}
    for v in vals:
        used = [it["id"] for it in items if it.get("type") == "A2" and it["gate"] == gate and it["drug_id"] == "GEN"]
        gen.append(("공통", "", "", "", label, "notes:" + tg, v[:600], tg[tg.find("p."):].rstrip(")") if "p." in tg else "", pdf_where(v, tg[tg.find("p."):].rstrip(")") if "p." in tg else ""), len(used), " ".join(used)))

ARIAL = "Arial"
H = Font(name=ARIAL, bold=True, color="FFFFFF", size=10); HF = PatternFill("solid", fgColor="305496")
FILLIN = PatternFill("solid", fgColor="FFFF00"); FILLIN_H = PatternFill("solid", fgColor="BF8F00")
N = Font(name=ARIAL, size=10); WRAP = Alignment(wrap_text=True, vertical="top")
thin = Side(style="thin", color="BFBFBF"); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)

wb = Workbook(); g = wb.active; g.title = "안내"
guide = [
    ("CSV 원문 대조 검수표", True),
    ("목적: 모든 문항(A형 107, A2형 38, C형 198)은 이 CSV(보험가이드북을 옮긴 44행 표)에서 코드가 정답을 만든다. 문항을 하나씩 보는 대신 CSV 값을 가이드북 PDF와 대조하면, 그 값을 쓰는 문항 정답이 한꺼번에 확인된다.", False),
    ("", False),
    ("작성 방법", True),
    ("1. 'CSV 칸' 시트에서 행마다 'CSV 값'을 PDF와 대조한다. 'PDF 장'은 값의 앞부분을 PDF에서 찾은 위치('값 검색')이거나, 못 찾으면 책 쪽을 PDF 장으로 바꾼 위치('책 쪽 환산', PDF 1장 = 책 2쪽)이고, '책 쪽'은 가이드북 인쇄 쪽 번호다.", False),
    ("2. 노란 칸만 채운다: 판정(일치 / 불일치 / 확인 불가), 올바른 값, 검수자, 코멘트.", False),
    ("3. '영향 문항 수'가 큰 행부터 보면 효율적이다 (값 하나가 여러 문항의 정답이 된다).", False),
    ("4. '공통 규칙' 시트는 약과 무관한 일반 급여 규칙(p.11·12·58·59)이다.", False),
    ("5. 불일치가 있으면 연구팀이 CSV를 고치고 문항을 다시 생성한다 (생성 코드: make_a.py, make_a2.py, make_c.py).", False),
    ("", False),
    ("작성 예시 (실제 행 아님): 판정 '불일치' | 올바른 값 'PCDAI 30 이상' | 검수자 '홍길동' | 코멘트 'p.35 고시 원문 확인'", False),
    ("범례: 노란색 = 검수자가 채우는 칸. 출처: data/IBD보험가이드북.csv (44행), insurance_guide_book_2024.pdf (31장).", False),
]
for i, (t, b) in enumerate(guide, 1):
    c = g.cell(row=i, column=1, value=t); c.font = Font(name=ARIAL, size=14 if i == 1 else 10, bold=b); c.alignment = WRAP
g["A11"].fill = FILLIN; g.column_dimensions["A"].width = 130

cols = [("번호", 6), ("drug_id", 18), ("약(국문)", 18), ("질환", 7), ("연령군", 9), ("칸 이름", 18), ("CSV 열", 16), ("CSV 값", 60),
        ("책 쪽", 14), ("PDF 장", 14), ("영향 문항 수", 8), ("영향 문항 ID", 40), ("판정", 11), ("올바른 값", 30), ("검수자", 10), ("코멘트", 30)]
FILLC = {"판정", "올바른 값", "검수자", "코멘트"}
def sheet(name, data):
    ws = wb.create_sheet(name)
    for ci, (h, w) in enumerate(cols, 1):
        c = ws.cell(row=1, column=ci, value=h); c.font = H; c.fill = FILLIN_H if h in FILLC else HF
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center"); c.border = BOX
        ws.column_dimensions[c.column_letter].width = w
    data = sorted(data, key=lambda x: (-x[9], x[0], x[4]))
    for ri, rec in enumerate(data, 2):
        for ci, v in enumerate((ri - 1,) + rec + (None, None, None, None), 1):
            c = ws.cell(row=ri, column=ci, value=v); c.font = N; c.alignment = WRAP; c.border = BOX
            if cols[ci - 1][0] in FILLC:
                c.fill = FILLIN
    last = len(data) + 1
    dv = DataValidation(type="list", formula1='"일치,불일치,확인 불가"', allow_blank=True); ws.add_data_validation(dv); dv.add(f"M2:M{last}")
    ws.freeze_panes = "H2"; ws.auto_filter.ref = f"A1:P{last}"
    return last
l1 = sheet("CSV 칸", recs); l2 = sheet("공통 규칙", gen)

s = wb.create_sheet("요약"); s["A1"] = "검수 진행 요약 (수식)"; s["A1"].font = Font(name=ARIAL, size=12, bold=True)
R = f"'CSV 칸'!$M$2:$M${l1}"
tab = [("대조할 칸 수", f"=COUNTA('CSV 칸'!$B$2:$B${l1})"), ("판정 완료", f"=COUNTA({R})"), ("진행률", "=IFERROR(B4/B3,0)"),
       ("일치", f'=COUNTIF({R},"일치")'), ("불일치", f'=COUNTIF({R},"불일치")'), ("확인 불가", f'=COUNTIF({R},"확인 불가")'),
       ("불일치 칸이 영향 주는 문항 수(합)", f"=SUMIF({R},\"불일치\",'CSV 칸'!$K$2:$K${l1})"),
       ("공통 규칙 판정 완료", f"=COUNTA('공통 규칙'!$M$2:$M${l2})")]
for i, (k, f) in enumerate(tab, 3):
    s.cell(row=i, column=1, value=k).font = N; s.cell(row=i, column=2, value=f).font = N
s["B5"].number_format = "0.0%"; s.column_dimensions["A"].width = 34
wb.save(OUT)
print("saved", OUT, "CSV 칸", len(recs), "공통", len(gen), "값 검색 성공", sum(1 for r in recs if "값 검색" in r[8]))
