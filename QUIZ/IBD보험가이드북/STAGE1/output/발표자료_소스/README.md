# 발표 자료 소스 (2026-11-16)

- `build.js` : 36장 덱(v3, Claude Opus 5.5 비교 4장 포함: 방법·정확도·안전 오답·Opus 기준 발견)을 만든다. 대본(발표자 노트)은 `notes.json`에서 슬라이드 제목으로 찾아 넣는다.
- `build_v5.js` + `notes_v5.json` : 2026-11-16 35장 v2 덱(`IBD_RAG_평가_발표_20261116_v2.pptx`) 소스, 보존용.
- `build_v4.js` + `notes_v4.json` : 2026-11-16 오전 32장 미팅용 덱(`IBD_RAG_평가_발표_20261116_미팅.pptx`) 소스, 보존용.
- `build_v3.js` : 2026-11-15 v2 덱(28장) 소스, 보존용.
- `make_script_md.py` : 덱의 발표자 노트와 `notes.json` 순서를 대조하고 `발표대본_*.md`를 만든다.
- 다시 만들기 (이 폴더에서, pptxgenjs 설치 후):
  - `npm install` → `node build.js ../IBD_RAG_평가_발표_20261116_v3.pptx`
  - `python3 make_script_md.py ../IBD_RAG_평가_발표_20261116_v3.pptx ../발표대본_20261116_v3.md`
  - 32장 판: `build_v4.js`와 `notes_v4.json`을 `build.js`·`notes.json` 이름으로 바꿔 같은 방법으로.
- 숫자는 모두 eval_out/ 결과 파일과 보고서(오답원인분류·인용문원문대조·오답위험도·모델비교·모델별발견)에서 옮겼다. 덱 만들기에는 API를 쓰지 않는다.
