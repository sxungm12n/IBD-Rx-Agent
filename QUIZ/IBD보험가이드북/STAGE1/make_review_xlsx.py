"""IBD 보험가이드북 문항 임상의 검수표 (A형·A2형·C형·D형)(xlsx) 생성. API 호출 없음. 사용: python3 make_review_xlsx.py <STAGE1 dir> <out.xlsx>"""
import json, sys, collections, math, random, re
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
    """evolve.py의 묶음 키와 같다: 평가 시점, 그리고 '함께 써도 정답' 중 시점 대안·고령 함정의 체크리스트 인용 허용은 뺀다."""
    k = {a: b for a, b in it["answer"]["채점"].items() if a != "시점"}
    alt = k.get("함께 써도 정답")
    if (isinstance(alt, dict) and set(alt) <= {"시점", "이유"}) or (it["기준"].startswith("고령") and isinstance(alt, str)):
        k.pop("함께 써도 정답")
    return it["기준"] + "|" + json.dumps(k, ensure_ascii=False, sort_keys=True)

main = [it for it in items if not it["기준"].startswith("금기") and it.get("type", "A") == "A"]
clusters = collections.defaultdict(list)
for it in main:
    clusters[ckey(it)].append(it["id"])
cl_no = {}
for n, (k, ids) in enumerate(sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0])), 1):
    for i in ids:
        cl_no[i] = (n, len(ids))

def _ids(name):
    p = ST / "output" / name
    return set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()
REASK, REGRADE = _ids("redo_ids_20261112.json"), _ids("regrade_ids_20261112.json")
CHANGED = REASK | REGRADE

# 1차 검수 표본: 유형 × 기준(결정 기준)별로 20%(올림, 최소 1문항). 시드 고정 → 누가 만들어도 같은 표본
def stratum(it):
    t = it.get("type", "A")
    return t + "|" + (it["gate"] if t == "C" else it["기준"])
rng = random.Random(20261112)
by = collections.defaultdict(list)
for it in sorted(items, key=lambda x: x["id"]):
    by[stratum(it)].append(it["id"])
SAMPLE = set()
for k in sorted(by):
    ids = by[k]
    if k.startswith("D|"):  # D형은 사례마다 판단 경로가 달라 전부 본다
        SAMPLE |= set(ids)
        continue
    SAMPLE |= set(rng.sample(ids, max(1, math.ceil(len(ids) * 0.2))))

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
    if iid in REASK:
        f.append("질문을 고친 문항(예전 답은 다시 받음). 새 질문 표현이 적절한지 확인")
    elif iid in REGRADE:
        f.append("채점 열쇠('함께 써도 정답' 등)를 보강한 문항. 허용 범위가 적절한지 확인")
    if gate == "G6":
        f.append("기준이 체크리스트 쪽에 있음. 체크리스트 원문과 대조")
        if "×10" in str(it["answer"]["정답"]):
            f.append("단위 환산(×10⁹/L ↔ cells/mm³) 확인")
        if iid == "A-FIL-UC-G6-alc":
            f.append("가이드북 원문이 림프구수를 '(ANC)'로 오기. 정답은 림프구(ALC) 기준(2026-11-11 결정)")
    if gate == "E" and "함께 써도 정답" in key and "시점" in key.get("함께 써도 정답", {}):
        f.append("가이드북 쪽마다 평가 시점이 다름. 고시문 시점을 정답, 다른 쪽 문구는 함께 써도 정답(2026-11-11 결정). PDF로 확인")
    if gate == "E" and re.search(r"(?<!\d)2주", str(key.get("시점", ""))):  # '12주'·'16주'는 제외
        f.append("'첫 투약 후 2주 내'는 PDF 원본과 심평원 고시(2025-189호)에서도 같음을 확인(2026-11-11)")
    if gate == "G2" and "적혀 있지 않다" in str(it["answer"]["정답"]):
        f.append("대조 문항(정답: 연령 조건 없음)")
    if gate == "G5" and key.get("조항") is False:
        f.append("대조 문항(정답: 65세 이상 추가 조건 없음)")
    if it.get("type") == "D":
        f.append("D형 약제 선택(보기 없이 묻고 코드 판정). 인정 목록과 (참고) 제외 이유가 가이드북과 맞는지, 환자 설명이 현실적인지 확인. 판단 원칙은 '결정확인' 시트 8~14번")
        if key.get("함정"):
            f.append("함정: " + key["함정"])
    if it.get("type") == "C":
        f.append("C형 환자 사례(코드 판정). 사례가 현실적인지, 판정·이유가 가이드북과 맞는지 확인. 판단 원칙은 '결정확인' 시트 8~11·15번")
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
    ("IBD 보험가이드북 문항 임상의 검수표 (A형·A2형·C형·D형)", BOLD),
    ("목적: 보험가이드북(2024 KASID Ver.3)으로 자동 생성한 A형·A2형·C형·D형 380문항의 질문·정답·판정이 PDF 원본과 맞는지 임상의가 확인한다. 논문 방법에 '임상의가 원문과 대조해 검수'로 보고된다.", NORMAL),
    ("", NORMAL),
    ("검수 순서 (1차)", BOLD),
    ("① 별도 파일 '검수표_CSV원문대조.xlsx': 모든 정답이 나오는 CSV 칸(280칸 + 공통 규칙 4칸)을 PDF와 대조한다. 영향이 큰 칸부터 정렬되어 있다.", NORMAL),
    ("② 이 파일의 '결정확인' 시트: 가이드북 해석이 필요했던 곳에서 연구팀이 정한 원칙 18개에 동의하는지 표시한다.", NORMAL),
    ("③ '문항검수' 시트에서 '1차 표본'이 '예'인 행을 검토한다(A·A2·C형은 유형·기준별 20%·최소 1문항, D형은 사례마다 판단 경로가 달라 37문항 전부. 시드 고정). 문제가 나온 유형·기준은 같은 유형·기준 전체로 넓힌다.", NORMAL),
    ("", NORMAL),
    ("작성 방법", BOLD),
    ("1. 노란색 칸만 채운다 (판정, 수정 정답, 질문 표현 수정안, 검수자, 코멘트 / 결정 확인 시트는 동의 여부, 의견, 검수자).", NORMAL),
    ("2. '확인할 PDF 쪽'의 원본 PDF를 열어 '정답'과 '원문 근거'가 원본과 같은지 본다. 근거 문장은 PDF를 옮겨 적은 텍스트에서 가져온 것이라 오탈자가 있을 수 있다.", NORMAL),
    ("3. 판정은 목록에서 고른다: 적합 / 정답 수정 / 질문 수정 / 삭제.", NORMAL),
    ("4. '확인 포인트'는 연구팀이 미리 표시한 주의 사항이다. 비어 있어도 그 행 전체를 검토한다.", NORMAL),
    ("5. 검수자 2인은 서로의 판정을 보지 않고 각자 파일에 작성한다. 불일치는 합의로 정한다.", NORMAL),
    ("6. 모델의 답과 점수는 일부러 넣지 않았다 (판정이 결과에 끌리지 않게).", NORMAL),
    ("", NORMAL),
    ("작성 예시 (실제 문항 행이 아님)", BOLD),
    ("판정: 정답 수정 | 수정 정답: 첫 투약 후 2주 내 평가 → PDF p.35는 '첫 투약 후 ○주'로 되어 있음 | 검수자: 홍길동 | 코멘트: 옮겨 적기 오류로 보임", NORMAL),
    ("", NORMAL),
    ("용어: 함께 써도 정답 = 써도 감점하지 않는 표현 / 참고(필수 아님) = 채점하지 않음 / 묶음 = 평가 시점을 뺀 채점 열쇠가 같은 A형 문항 모음(30묶음)", NORMAL),
    ("범례: 노란색 = 검수자가 채우는 칸 / 파란 머리글 = 연구팀이 채운 칸 (수정하지 않음)", NORMAL),
    ("출처: output/a_items.jsonl · a2_items.jsonl · c_items.jsonl · d_items.jsonl (make_a·make_a2·make_c·make_d.py 생성, 2026-11-12 문항)", NORMAL),
]
for r, (t, f) in enumerate(lines, 1):
    c = g.cell(row=r, column=1, value=t); c.font = f; c.alignment = Alignment(wrap_text=True, vertical="top")
g.column_dimensions["A"].width = 130
g["A1"].font = Font(name=ARIAL, size=14, bold=True)
g["A18"].fill = FILLIN

# ---------------- 문항검수
ws = wb.create_sheet("문항검수")
cols = [("번호", 6), ("문항 ID", 22), ("기준", 12), ("본 점수 포함", 8), ("약", 26), ("질문", 40), ("정답", 44),
        ("채점 열쇠", 40), ("원문 근거", 50), ("확인할 PDF 쪽", 14), ("묶음 번호", 7), ("같은 묶음 문항 수", 8),
        ("확인 포인트", 44), ("1차 표본", 7), ("판정", 12), ("수정 정답", 30), ("질문 표현 수정안", 30), ("검수자", 10), ("코멘트", 30)]
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
    if isinstance(ans, dict):  # D형(보기 없음): 인정 목록 + 정답 계산 때의 제외 이유(참고)
        why = ans.get("제외") or it.get("제외 이유(참고)", {})
        ans = "인정: " + (", ".join(ans["인정"]) or "없음") + "\n(참고) 제외: " + "; ".join(f"{d} - {w}" for d, w in why.items())
    elif isinstance(ans, list):
        ans = "\n".join(ans)
    n, size = cl_no.get(it["id"], ("", ""))
    vals = [r - 1, it["id"], it["기준"], ("A2형" if it.get("type") == "A2" else "C형" if it.get("type") == "C" else "D형" if it.get("type") == "D" else ("아니오" if it["기준"].startswith("금기") else "예")), it["drug_name"], it["question"], ans,
            json.dumps(it["answer"]["채점"], ensure_ascii=False), it["원문"], it["source_page"], n, size, flags(it),
            "예" if it["id"] in SAMPLE else "", None, None, None, None, None]
    for ci, v in enumerate(vals, 1):
        c = ws.cell(row=r, column=ci, value=v); c.font = NORMAL; c.alignment = WRAP; c.border = BOX
        if cols[ci - 1][0] in FILL_COLS:
            c.fill = FILLIN
last = len(rows) + 1
dv = DataValidation(type="list", formula1='"적합,정답 수정,질문 수정,삭제"', allow_blank=True)
dv.error = "목록에서 고르세요"; dv.prompt = "적합 / 정답 수정 / 질문 수정 / 삭제"
ws.add_data_validation(dv); dv.add(f"O2:O{last}")
ws.freeze_panes = "C2"
ws.auto_filter.ref = f"A1:S{last}"
ws["M1"].comment = Comment("연구팀이 미리 표시한 주의 사항. 비어 있어도 전체 검토.", "연구팀")

# ---------------- 결정 확인 (연구팀이 정한 해석 원칙)
DECISIONS = [
    ("정답 기준", "가이드북 쪽마다 평가 시점이 다르면 고시문을 정답으로 하고, 다른 쪽 문구는 '함께 써도 정답'으로 둔다. (Ozanimod 고시 10~20주 vs 비교표 10~22주 / Vedolizumab SC 고시 14주 이내 vs 투약간격 그림 'IV 2회 후' / Infliximab 누공 고시 3회 후 vs 비교표 14주 이내)", "A-OZA-UC-E, A-VEDO-SC-*-E, A-IFX-IV-CD-fistula-E", "p.23·27·29·35·44·45·56"),
    ("정답 기준", "고령·고위험 문항은 질문이 65세 이상·심혈관계 고위험군·악성 종양 위험을 모두 묻고, 정답도 세 대상 모두를 요구한다.", "A형 G5 7문항 (함정 3문항은 추가 조건 없음이 정답)", "p.27·48~55"),
    ("채점", "활성도 점수 기준이 없는 대상(누공성 크론병, 장형 베체트)은 '점수 기준 없음'만 써도 맞음. 대상 설명은 써도 되고 안 써도 된다.", "A형 활성도 함정 4문항", "p.23·37·42"),
    ("채점", "이전 치료 문항은 반응 없음·내약성 없음·금기 세 조항을 모두 써야 맞음.", "A형 이전 치료 25문항", "p.35~57 고시문"),
    ("채점", "평가 시점은 핵심 요소가 아니다. 나머지가 맞고 시점만 틀리면 부분 점수.", "A형 유지 기준 25문항", "-"),
    ("채점", "하한을 묻는 문항에서 'N 미만'은 결과(투여 불가·보류)를 함께 써야 'N 이상'과 같은 뜻으로 본다.", "A형 검사 하한 12문항", "p.49·52·54"),
    ("가이드북 오기", "Filgotinib 체크리스트의 '절대 림프구수(ANC) 0.5×10⁹/L'를 림프구수(ALC)의 오기로 보고 정답을 ALC 0.5×10⁹/L로 한다.", "A-FIL-UC-G6-alc, C-FIL-UC-alc-low, D형 ALC 사례", "p.49"),
    ("사례 판정", "소아 궤양성 대장염 활성도는 PUCAI '45 초과'이므로 PUCAI 45는 불인정.", "C-IFX-IV-UC-ped-act-low, D-puc-45", "p.26·36"),
    ("사례 판정", "검사 하한(Hb·ANC·ALC)과 Ozanimod의 '최근 6개월 이내 심근경색 등'은 고시가 아니라 투여 전 체크리스트(투여 불가·보류)에 있다. C·D형 질문은 '사례에 적히지 않은 투여 전 확인사항(결핵·감염·임신 등)은 모두 문제없는 것으로 본다. 가이드북의 급여 기준으로 판단할 때(사례에 검사 수치·병력이 있으면 투여 전 확인사항도 적용)'로 묻는다.", "C형 시작 판정 142문항, D형 37문항", "p.49·52·54·56"),
    ("사례 판정", "소분자제제(JAK 3종·Ozanimod) 사례와 45세 등 가임기 연령 성인 D형 사례는 남성으로 한다. 체크리스트에 '임신 가능성이 있는 여성 투여 불가·보류'가 있기 때문이다.", "C형 소분자 사례, D형 성인 사례", "p.49·52·54·56"),
    ("사례 판정", "소아 UC 유지의 'PUCAI가 기준보다 20점 이상 감소'에서 '기준'을 투여 전 점수로 읽든 진입 기준 45로 읽든 같은 답이 나오도록 인정 사례는 65→25, 불인정 사례는 60→45로 한다.", "C-IFX-IV-UC-ped-maint-ok/ng", "p.36"),
    ("약제 범위", "'해당 없음' 규칙: 누공성 크론병은 Infliximab만 / 소아 크론병은 Infliximab·Adalimumab만 / 소아 궤양성 대장염은 Infliximab만 / 소분자제제는 소아 해당 없음 / Golimumab·Tofacitinib·Filgotinib·Ozanimod는 궤양성 대장염만 / 장형 베체트는 Infliximab(만 19세 이상)·Adalimumab만. 약은 성분 단위로 채점하고, 정맥주사 한정(램시마 SC는 소아·베체트 고시 없음)은 채점하지 않는다.", "D형 전체, C형 일부", "p.23·26·27·37·38~39·42"),
    ("약제 범위", "장형 베체트 18세: 고시에 Adalimumab의 나이 조건이 없으므로 인정, Infliximab은 만 19세 이상이라 제외. (국내 허가가 성인으로 한정되는지는 PDF로 확인하지 못함)", "D-bd-18", "p.37·42"),
    ("약제 범위", "JAK 억제제는 65세 이상·심혈관계 고위험군·악성 종양 위험 환자에서 생물학제제 실패가 필요하다(사례에 '심혈관계 고위험군'을 직접 적음). Ozanimod는 고령·고위험 조항이 없어 68세·심혈관 고위험(5년 전 심근경색)에서도 인정, 4개월 전 심근경색은 체크리스트 금기로 제외.", "D-cd-cv, D-uc-cv, D-uc-recent-mi, C-*-old-*", "p.27·56"),
    ("사례 판정", "궤양성 대장염에서 메살라진(5-ASA)만 실패한 경우는 불인정. UC 고시는 'Corticosteroid나 6-MP 또는 Azathioprine 등'을 명시하고 5-ASA는 쓰지 않는다(장형 베체트 고시는 5-ASA를 명시).", "C형 UC prior-short 12문항(소아 포함), D-uc-5asa", "p.36·37·42"),
    ("A2형 범위", "용량 증량 13문항은 급여 기준이 아니라 비교표의 허가사항 기반 용법(Dose escalation 행)이다. 가이드북에 적힌 내용으로만 채점하고 기준 혼동 분석에서는 대조 영역으로 쓴다.", "A2형 용량 증량 13문항", "p.23·26·27"),
    ("A2형 범위", "Adalimumab·Golimumab 처방 기간은 비교표 '기타' 행의 병합 칸('SC 제형 투여 24주 이후 12주분 장기 처방')이 Remsima SC부터 Simponi 열까지 걸쳐 있으므로 해당한다고 본다.", "A2-ADA-*-L, A2-GOL-UC-L", "p.23·26"),
    ("A형 범위", "5-ASA 소아 연령(6세 이상)은 급여 조건이 아니라 용법·용량 표의 연령이다. 질문을 '가이드북에 적힌 연령(체중) 조건'으로 묻는다.", "A형 5-ASA 나이 4문항", "p.17"),
    ("D형 정답", "TNF 억제제(Adalimumab)에 반응이 없었던 환자에서 이미 실패한 약은 정답(급여 인정 약)에서 뺀다. 답에 쓰면 틀림으로 채점한다.", "D형 TNF 실패 사례 5문항", "p.44·45 (교체투여)"),
    ("사례 판정", "Vedolizumab IV와 SC(킨텔레스 SC)는 투여대상이 같은 고시로 묶여 있다. SC는 300mg IV 2회 후 SC로 이어 가는 용법이므로, 투여대상 조건을 만족하면 SC 사례도 '급여 대상: 예'로 본다. (에이전트는 'IV 2회를 먼저 맞지 않았으니 아니오'로 답한 경우가 있어 문구 확인 필요)", "C-VEDO-SC-* 14문항", "p.29·44·45"),
]
dsh = wb.create_sheet("결정확인")
dcols = [("번호", 6), ("구분", 12), ("연구팀이 정한 원칙", 80), ("적용 문항", 30), ("확인할 PDF 쪽", 16), ("동의 여부", 12), ("의견 (수정 필요 시 대안)", 40), ("검수자", 10)]
for ci, (name, w) in enumerate(dcols, 1):
    c = dsh.cell(row=1, column=ci, value=name)
    c.font = H; c.fill = FILLIN_H if name in ("동의 여부", "의견 (수정 필요 시 대안)", "검수자") else HF
    c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center"); c.border = BOX
    dsh.column_dimensions[c.column_letter].width = w
for r, (kind, rule, where, page) in enumerate(DECISIONS, 2):
    for ci, v in enumerate([r - 1, kind, rule, where, page, None, None, None], 1):
        c = dsh.cell(row=r, column=ci, value=v); c.font = NORMAL; c.alignment = WRAP; c.border = BOX
        if ci >= 6:
            c.fill = FILLIN
assert len(DECISIONS) == 20, "요약 시트 수식 범위(2~21행)와 맞출 것"
ddv = DataValidation(type="list", formula1='"동의,수정 필요,판단 보류"', allow_blank=True)
dsh.add_data_validation(ddv); ddv.add(f"F2:F{len(DECISIONS) + 1}")
dsh.freeze_panes = "C2"

# ---------------- 요약 (수식)
s = wb.create_sheet("요약")
s["A1"] = "검수 진행 요약 (수식으로 자동 계산)"; s["A1"].font = Font(name=ARIAL, size=12, bold=True)
R = f"문항검수!$O$2:$O${last}"
table = [("전체 문항", f"=COUNTA(문항검수!$B$2:$B${last})"),
         ("본 점수 포함 문항", f'=COUNTIF(문항검수!$D$2:$D${last},"예")'),
         ("판정 완료", f"=COUNTA({R})"),
         ("진행률", "=IFERROR(B5/B3,0)"),
         ("적합", f'=COUNTIF({R},"적합")'),
         ("정답 수정", f'=COUNTIF({R},"정답 수정")'),
         ("질문 수정", f'=COUNTIF({R},"질문 수정")'),
         ("삭제", f'=COUNTIF({R},"삭제")'),
         ("확인 포인트가 있는 문항", f'=COUNTIF(문항검수!$M$2:$M${last},"?*")'),
         ("1차 표본 문항", f'=COUNTIF(문항검수!$N$2:$N${last},"예")'),
         ("1차 표본 중 판정 완료", f'=COUNTIFS(문항검수!$N$2:$N${last},"예",{R},"?*")'),
         ("결정 확인: 동의", '=COUNTIF(결정확인!$F$2:$F$21,"동의")'),
         ("결정 확인: 수정 필요", '=COUNTIF(결정확인!$F$2:$F$21,"수정 필요")')]
for r, (k, f) in enumerate(table, 3):
    s.cell(row=r, column=1, value=k).font = NORMAL
    c = s.cell(row=r, column=2, value=f); c.font = NORMAL
s["B6"].number_format = "0.0%"
s.column_dimensions["A"].width = 26; s.column_dimensions["B"].width = 12
wb.save(OUT)
print("saved", OUT, "rows", len(rows), "1차 표본", len(SAMPLE), "결정", len(DECISIONS))
