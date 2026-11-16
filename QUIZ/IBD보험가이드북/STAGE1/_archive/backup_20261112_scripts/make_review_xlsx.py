"""IBD 보험가이드북 문항 임상의 검수표 (A형·A2형·C형)(xlsx) 생성. API 호출 없음. 사용: python3 make_review_xlsx.py <STAGE1 dir> <out.xlsx>"""
import json, sys, collections
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment

ST = Path(sys.argv[1]); OUT = Path(sys.argv[2])
items = [json.loads(l) for l in (ST / "output/a_items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
A2 = ST / "output/a2_items.jsonl"
if A2.exists():  # A2형 (2026-11-11, CSV 메모의 추가 급여 규칙)
    items += [json.loads(l) for l in A2.read_text(encoding="utf-8").splitlines() if l.strip()]
D = ST / "output/d_items.jsonl"
if D.exists():  # D형 약제 선택 (2026-11-11)
    items += [json.loads(l) for l in D.read_text(encoding="utf-8").splitlines() if l.strip()]
C = ST / "output/c_items.jsonl"
if C.exists():  # C형 환자 사례 판정 (2026-11-11)
    items += [json.loads(l) for l in C.read_text(encoding="utf-8").splitlines() if l.strip()]

def ckey(it):
    k = {a: b for a, b in it["answer"]["채점"].items() if a != "시점"}
    return it["기준"] + "|" + json.dumps(k, ensure_ascii=False, sort_keys=True)

main = [it for it in items if not it["기준"].startswith("금기") and it.get("type", "A") == "A"]
clusters = collections.defaultdict(list)
for it in main:
    clusters[ckey(it)].append(it["id"])
cl_no = {}
for n, (k, ids) in enumerate(sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0])), 1):
    for i in ids:
        cl_no[i] = (n, len(ids))

CHANGED = set(json.loads((ST / "output/changed_items_20261111.json").read_text(encoding="utf-8"))) if (ST / "output/changed_items_20261111.json").exists() else set()

def flags(it):
    f = []
    iid, gate, key = it["id"], it["gate"], it["answer"]["채점"]
    if gate == "G7":
        f.append("본 점수 제외(금기 체크리스트). 참고로만 검토")
    if gate == "G3" and key.get("척도", "x") is None:
        f.append("대조 문항(정답: 점수 기준 없음). 대상 설명은 '함께 써도 정답'(2026-11-11 결정)")
    if "-SC-" in iid or iid.startswith("A-IFX-SC") or iid.startswith("A-VEDO-SC"):
        f.append("약 이름을 'IV→SC'에서 피하주사 제품명으로 바꿈(2026-11-11). 표현이 적절한지 확인")
    if gate == "G5":
        f.append("질문을 세 대상(65세 이상·심혈관 고위험·악성종양 위험) 모두 묻도록 바꿈(2026-11-11). 정답도 세 대상 모두")
    if iid in CHANGED:
        f.append("2026-11-11 질문 또는 정답 변경 문항")
    if gate == "G6":
        f.append("기준이 체크리스트 쪽에 있음. 체크리스트 원문과 대조")
        if "×10" in str(it["answer"]["정답"]):
            f.append("단위 환산(×10⁹/L ↔ cells/mm³) 확인")
        if iid == "A-FIL-UC-G6-alc":
            f.append("가이드북 원문이 림프구수를 '(ANC)'로 오기. 정답은 림프구(ALC) 기준(2026-11-11 결정)")
    if gate == "E" and "함께 써도 정답" in key and "시점" in key.get("함께 써도 정답", {}):
        f.append("가이드북 쪽마다 평가 시점이 다름. 고시문 시점을 정답, 다른 쪽 문구는 함께 써도 정답(2026-11-11 결정). PDF로 확인")
    if gate == "E" and "2주" in str(key.get("시점", "")):
        f.append("'첫 투약 후 2주 내'는 PDF 원본과 심평원 고시(2025-189호)에서도 같음을 확인(2026-11-11)")
    if gate == "G2" and "적혀 있지 않다" in str(it["answer"]["정답"]):
        f.append("대조 문항(정답: 연령 조건 없음)")
    if gate == "G5" and key.get("조항") is False:
        f.append("대조 문항(정답: 65세 이상 추가 조건 없음)")
    if it.get("type") == "D":
        f.append("D형 약제 선택(코드 판정). 인정·제외 목록과 제외 이유가 가이드북과 맞는지, 환자 설명이 현실적인지 확인")
        if key.get("함정"):
            f.append("함정: " + key["함정"])
    if it.get("type") == "C":
        f.append("C형 환자 사례(코드 판정). 사례가 현실적인지, 판정·이유가 가이드북과 맞는지 확인")
        if key.get("함정"):
            f.append("함정: " + key["함정"])
    if it.get("type") == "A2":
        f.append("A2형(2026-11-11 추가): CSV 메모에서 코드로 만든 새 영역 문항")
        if iid.startswith("A2-GEN"):
            f.append("약과 무관한 공통 규칙")
        if gate == "D":
            f.append("허가사항 기반 용법(급여 기준인지 확인). 한국·외국 기준이 같을 수 있는 대조 영역")
        if iid == "A2-ADA-GIBD-L":
            f.append("베체트 행에는 '24주 이후 12주분' 문구가 없음(가이드북 표에 베체트 열 없음). 맞는지 확인")
        if gate == "L" and "IFX" not in iid and "VEDO" not in iid and "GOL" not in iid:
            f.append("'퇴원 2주분'(p.28)과 '24주 이후 12주분'(p.23·26) 두 규칙을 함께 정답으로 함")
    if iid in cl_no and cl_no[iid][1] >= 5:
        f.append(f"같은 내용 정답 {cl_no[iid][1]}문항(묶음 {cl_no[iid][0]}). 정답이 틀리면 모두 영향")
    return " / ".join(f)

ARIAL = "Arial"
H = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
HF = PatternFill("solid", fgColor="305496")
FILLIN = PatternFill("solid", fgColor="FFFF00")
FILLIN_H = PatternFill("solid", fgColor="BF8F00")
NORMAL = Font(name=ARIAL, size=10)
BOLD = Font(name=ARIAL, size=10, bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)

wb = Workbook()

# ---------------- 안내
g = wb.active; g.title = "안내"
lines = [
    ("IBD 보험가이드북 문항 임상의 검수표 (A형·A2형·C형)", BOLD),
    ("목적: 보험가이드북(2024 KASID Ver.3)으로 자동 생성한 A형·A2형·C형 문항의 질문·정답·판정이 PDF 원본과 맞는지 임상의가 확인한다. 논문 방법에 '임상의가 원문과 대조해 검수'로 보고된다.", NORMAL),
    ("", NORMAL),
    ("작성 방법", BOLD),
    ("1. '문항검수' 시트에서 노란색 칸만 채운다 (판정, 수정 정답, 질문 표현 수정안, 검수자, 코멘트).", NORMAL),
    ("2. '확인할 PDF 쪽'의 원본 PDF를 열어 '정답'과 '원문 근거'가 원본과 같은지 본다. 근거 문장은 PDF를 옮겨 적은 텍스트에서 가져온 것이라 오탈자가 있을 수 있다.", NORMAL),
    ("3. 판정은 목록에서 고른다: 적합 / 정답 수정 / 질문 수정 / 삭제.", NORMAL),
    ("4. '확인 포인트'는 연구팀이 미리 표시한 주의 사항이다. 비어 있어도 전체를 검토한다.", NORMAL),
    ("5. 검수자 2인은 서로의 판정을 보지 않고 각자 파일에 작성한다. 불일치는 합의로 정한다.", NORMAL),
    ("6. 모델의 답과 점수는 일부러 넣지 않았다 (판정이 결과에 끌리지 않게).", NORMAL),
    ("", NORMAL),
    ("작성 예시 (실제 문항 행이 아님)", BOLD),
    ("판정: 정답 수정 | 수정 정답: 첫 투약 후 2주 내 평가 → PDF p.35는 '첫 투약 후 ○주'로 되어 있음 | 검수자: 홍길동 | 코멘트: 옮겨 적기 오류로 보임", NORMAL),
    ("", NORMAL),
    ("함께 결정해 주실 것 (코멘트 칸이나 이 시트 아래에 적어 주세요)", BOLD),
    ("가. 누공성 크론병·장형 베체트의 '급여 활성도 기준은?' 대조 문항: 정답 '점수 기준 없음'에 더해 괄호 속 대상 설명까지 써야 맞음으로 볼까?", NORMAL),
    ("나. 'Infliximab IV→SC', 'Vedolizumab IV→SC' 문항의 약 이름 표현을 '피하주사(램시마 SC)'처럼 바꿀까?", NORMAL),
    ("", NORMAL),
    ("범례: 노란색 = 검수자가 채우는 칸 / 파란 머리글 = 연구팀이 채운 칸 (수정하지 않음)", NORMAL),
    ("출처: 문항 output/a_items.jsonl (make_a.py 생성, 2026-11-10 G5 정답지 4문항 수정 반영). 묶음 = 평가 시점을 뺀 채점 열쇠가 같은 문항 모음.", NORMAL),
]
for r, (t, f) in enumerate(lines, 1):
    c = g.cell(row=r, column=1, value=t); c.font = f; c.alignment = Alignment(wrap_text=True, vertical="top")
g.column_dimensions["A"].width = 130
g["A1"].font = Font(name=ARIAL, size=14, bold=True)
g["A13"].fill = FILLIN

# ---------------- 문항검수
ws = wb.create_sheet("문항검수")
cols = [("번호", 6), ("문항 ID", 22), ("기준", 12), ("본 점수 포함", 8), ("약", 26), ("질문", 40), ("정답", 44),
        ("채점 열쇠", 40), ("원문 근거", 50), ("확인할 PDF 쪽", 14), ("묶음 번호", 7), ("같은 묶음 문항 수", 8),
        ("확인 포인트", 44), ("판정", 12), ("수정 정답", 30), ("질문 표현 수정안", 30), ("검수자", 10), ("코멘트", 30)]
FILL_COLS = {"판정", "수정 정답", "질문 표현 수정안", "검수자", "코멘트"}
for ci, (name, w) in enumerate(cols, 1):
    c = ws.cell(row=1, column=ci, value=name)
    c.font = H; c.fill = FILLIN_H if name in FILL_COLS else HF
    c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center"); c.border = BOX
    ws.column_dimensions[c.column_letter].width = w
order = {"G2": 0, "G3": 1, "G4": 2, "E": 3, "G5": 4, "G6": 5, "G7": 6, "R": 7, "P": 8, "T": 9, "W": 10, "L": 11, "J": 12, "D": 13}
rows = sorted(items, key=lambda it: (order.get(it["gate"], 9), cl_no.get(it["id"], (99, 0))[0], it["id"]))
for r, it in enumerate(rows, 2):
    ans = it["answer"]["정답"]
    if isinstance(ans, dict):  # D형: 인정·제외
        ans = "인정: " + (", ".join(ans["인정"]) or "없음") + "\n제외: " + "; ".join(f"{d} - {w}" for d, w in ans["제외"].items())
    elif isinstance(ans, list):
        ans = "\n".join(ans)
    n, size = cl_no.get(it["id"], ("", ""))
    vals = [r - 1, it["id"], it["기준"], ("A2형" if it.get("type") == "A2" else "C형" if it.get("type") == "C" else "D형" if it.get("type") == "D" else ("아니오" if it["기준"].startswith("금기") else "예")), it["drug_name"], it["question"], ans,
            json.dumps(it["answer"]["채점"], ensure_ascii=False), it["원문"], it["source_page"], n, size, flags(it), None, None, None, None, None]
    for ci, v in enumerate(vals, 1):
        c = ws.cell(row=r, column=ci, value=v); c.font = NORMAL; c.alignment = WRAP; c.border = BOX
        if cols[ci - 1][0] in FILL_COLS:
            c.fill = FILLIN
last = len(rows) + 1
dv = DataValidation(type="list", formula1='"적합,정답 수정,질문 수정,삭제"', allow_blank=True)
dv.error = "목록에서 고르세요"; dv.prompt = "적합 / 정답 수정 / 질문 수정 / 삭제"
ws.add_data_validation(dv); dv.add(f"N2:N{last}")
ws.freeze_panes = "C2"
ws.auto_filter.ref = f"A1:R{last}"
ws["M1"].comment = Comment("연구팀이 미리 표시한 주의 사항. 비어 있어도 전체 검토.", "연구팀")

# ---------------- 요약 (수식)
s = wb.create_sheet("요약")
s["A1"] = "검수 진행 요약 (수식으로 자동 계산)"; s["A1"].font = Font(name=ARIAL, size=12, bold=True)
R = f"문항검수!$N$2:$N${last}"
table = [("전체 문항", f"=COUNTA(문항검수!$B$2:$B${last})"),
         ("본 점수 포함 문항", f'=COUNTIF(문항검수!$D$2:$D${last},"예")'),
         ("판정 완료", f"=COUNTA({R})"),
         ("진행률", "=IFERROR(B5/B3,0)"),
         ("적합", f'=COUNTIF({R},"적합")'),
         ("정답 수정", f'=COUNTIF({R},"정답 수정")'),
         ("질문 수정", f'=COUNTIF({R},"질문 수정")'),
         ("삭제", f'=COUNTIF({R},"삭제")'),
         ("확인 포인트가 있는 문항", f'=COUNTIF(문항검수!$M$2:$M${last},"?*")')]
for r, (k, f) in enumerate(table, 3):
    s.cell(row=r, column=1, value=k).font = NORMAL
    c = s.cell(row=r, column=2, value=f); c.font = NORMAL
s["B6"].number_format = "0.0%"
s.column_dimensions["A"].width = 26; s.column_dimensions["B"].width = 12
wb.save(OUT)
print("saved", OUT, "rows", len(rows))
