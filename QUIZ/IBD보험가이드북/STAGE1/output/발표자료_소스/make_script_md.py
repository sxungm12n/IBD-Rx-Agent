"""notes.json(슬라이드 제목 → 대본)과 덱의 발표자 노트 순서를 대조해 발표대본 .md를 만든다."""
import json, re, sys, zipfile, html
deck, out = sys.argv[1], sys.argv[2]
notes = json.load(open(sys.argv[3] if len(sys.argv) > 3 else "notes.json", encoding="utf-8"))  # 3번째 인자: 다른 대본 파일 (예: notes_10min.json)
z = zipfile.ZipFile(deck)
def num(n): return int(re.search(r"(\d+)\.xml$", n).group(1))
files = sorted([n for n in z.namelist() if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)], key=num)
deck_notes = []
for f in files:
    x = z.read(f).decode("utf-8")
    t = "".join(html.unescape(m) for m in re.findall(r"<a:t>([^<]*)</a:t>", x))
    deck_notes.append(t)
titles = list(notes)
assert len(titles) == len(deck_notes), (len(titles), len(deck_notes))
for i, (k, d) in enumerate(zip(titles, deck_notes), 1):
    assert notes[k] in d, f"slide {i} 순서 불일치: {k}"
SKIP = {"3주 동안 이렇게 진행했다", "채점 방식은 세 번 다듬었고, 최종은 v2.1이다", "에이전트가 가져온 5쪽을 ‘핵심 쪽’과 대조했다", "RAG 검색이 가져온 5쪽을 ‘핵심 쪽’과 대조했다",
        "모든 결과는 코드로 다시 만들 수 있게 남겼다", "논문을 키울 수 있는 추가 분석"}
RATE = 330  # 말하기 속도: 1분에 약 330자(공백 제외)
def mins(t): return len(t.replace(" ", "")) / RATE
total = sum(mins(notes[k]) for k in titles)
short = sum(mins(notes[k]) for k in titles if k not in SKIP)
L = ["# 발표 대본 · IBD 보험가이드북 RAG 에이전트 평가", "",
     f"- 슬라이드 {len(titles)}장. 대본만 읽으면 약 {round(total)}분, 질문 시간은 따로.",
     *([f"- 시간이 짧으면 '(건너뛰기 가능)' 표시 {sum(k in SKIP for k in titles)}장을 넘기면 약 {round(short)}분."] if any(k in SKIP for k in titles) else []),
     "- 같은 대본이 PPT·Google Slides의 발표자 노트에도 들어 있다(발표자 보기에서 보임).",
     "- 숫자는 모두 답 1회 · 채점 1회분이며 임상의 검증 전이다.", ""]
for i, k in enumerate(titles, 1):
    tag = " (건너뛰기 가능)" if k in SKIP else ""
    L += [f"## {i}. {k}{tag} · 약 {max(0.5, round(mins(notes[k]) * 2) / 2):g}분", "", notes[k], ""]
open(out, "w", encoding="utf-8").write("\n".join(L))
print("ok", len(titles), round(total, 1), round(short, 1))
