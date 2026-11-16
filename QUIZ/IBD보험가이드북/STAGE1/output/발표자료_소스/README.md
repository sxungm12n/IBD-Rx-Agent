# 발표 자료 소스 (2026-11-16)

- `build.js` : 40장 덱(v5, 다른 모델 8장: Opus 4장 + Qwen 2장 + 세 모델 오류 분석·개선 방향 2장)을 만든다. 대본(발표자 노트)은 `notes.json`에서 슬라이드 제목으로 찾아 넣는다.
- `build_v5.js` + `notes_v5.json` : 2026-11-16 35장 v2 덱(`IBD_RAG_평가_발표_20261116_v2.pptx`) 소스, 보존용.
- `build_v4.js` + `notes_v4.json` : 2026-11-16 오전 32장 미팅용 덱(`IBD_RAG_평가_발표_20261116_미팅.pptx`) 소스, 보존용.
- `build_v3.js` : 2026-11-15 v2 덱(28장) 소스, 보존용.
- `make_script_md.py` : 덱의 발표자 노트와 `notes.json` 순서를 대조하고 `발표대본_*.md`를 만든다.
- 다시 만들기 (이 폴더에서, pptxgenjs 설치 후):
  - `npm install` → `node build.js ../IBD_RAG_평가_발표_20261116_v5.pptx`
  - `python3 make_script_md.py ../IBD_RAG_평가_발표_20261116_v5.pptx ../발표대본_20261116_v5.md`
  - 32장 판: `build_v4.js`와 `notes_v4.json`을 `build.js`·`notes.json` 이름으로 바꿔 같은 방법으로.
- 숫자는 모두 eval_out/ 결과 파일과 보고서(오답원인분류·인용문원문대조·오답위험도·모델비교·모델별발견)에서 옮겼다. 덱 만들기에는 API를 쓰지 않는다.
- 2026-11-16 저녁: `build.js`·`notes.json`은 38장 v4(Qwen3-14B 공개 모델 2장 추가, 안전 오답 슬라이드에 Qwen 열)로 바뀜 → `IBD_RAG_평가_발표_20261116_v4.pptx`, `발표대본_20261116_v4.md`. 바꾸기 전 36장 v3 소스는 `build_v6.js` + `notes_v6.json`으로 보존.
- 2026-11-16 밤: 40장 v5(세 모델 오류 분석 2장 추가) → `IBD_RAG_평가_발표_20261116_v5.pptx`, `발표대본_20261116_v5.md`. 38장 v4 소스는 `build_v7.js` + `notes_v7.json`으로 보존.
