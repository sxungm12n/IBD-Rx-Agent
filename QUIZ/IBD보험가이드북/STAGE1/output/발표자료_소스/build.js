const pptxgen = require("pptxgenjs");
const { applyTheme } = require("./apply_theme.js");

const OUT = process.argv[2] || "deck.pptx";
const THEME = {
  name: "IBD RAG Eval",
  headFontFace: "맑은 고딕",
  bodyFontFace: "맑은 고딕",
  colors: {
    dk1: "16283A", lt1: "FFFFFF", dk2: "3E4C59", lt2: "EEF2F5",
    accent1: "1F5F8B", accent2: "C9772B", accent3: "5F6B76", accent4: "94501A",
    accent5: "9CC3DE", accent6: "C9D6DF", hlink: "1F5F8B", folHlink: "5F6B76",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "IBD 보험가이드북 RAG 기능 추가 평가";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const SH = pres.shapes;

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "eyebrow", type: "body", x: 0.8, y: 1.75, w: 11.5, h: 0.4, fontSize: 14, bold: true, color: C.accent5, align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.25, w: 11.5, h: 1.9, fontSize: 44, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.35, w: 10.8, h: 1.2, fontSize: 18, color: C.accent6, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.6, 0.6, 0.7, 0.6],
  objects: [
    { placeholder: { options: { name: "eyebrow", type: "body", x: 0.6, y: 0.38, w: 12.1, h: 0.32, fontSize: 12, bold: true, color: C.accent1, align: "left", margin: 0, charSpacing: 1 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.72, w: 12.1, h: 0.75, fontSize: 28, bold: true, color: C.text1, valign: "top", align: "left", margin: 0 }, text: "" } },
    { text: { text: "IBD 보험가이드북 RAG 기능 추가 평가 · 2026-11-16", options: { x: 0.6, y: 6.98, w: 8, h: 0.3, fontSize: 10, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: 12.13, y: 6.98, w: 0.6, h: 0.3, fontSize: 10, color: C.accent3, align: "right", margin: 0 },
});

// ---------- notes (발표 대본: notes.json, 슬라이드 제목 → 대본) ----------
const NOTES = require("./notes.json");
const USED = new Set();
function addNote(s) {
  const t = NOTES[s._title];
  if (!t) throw new Error("대본 없음: " + s._title);
  s.addNotes(t);
  USED.add(s._title);
}

// ---------- helpers ----------
let n = 0;
function content(eyebrow, title, section) {
  const opts = { masterName: "CONTENT" };
  if (section) opts.sectionTitle = section;
  const s = pres.addSlide(opts);
  s.addText(eyebrow, { placeholder: "eyebrow" });
  s.addText(title, { placeholder: "title" });
  s._title = title;
  return s;
}
function card(s, x, y, w, h, fill) {
  n += 1;
  s.addShape(SH.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill || C.background2 }, line: { color: fill || C.background2 }, rectRadius: 0.08, objectName: `card-${n}` });
}
function tx(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, margin: 0, fontSize: 16, color: C.text2, valign: "top", paraSpaceAfter: 4 }, o));
}
function label(s, text, x, y, w, color) {
  tx(s, text, { x, y, w, h: 0.32, fontSize: 13, bold: true, color: color || C.accent1 });
}
function callout(s, text, x, y, w, h, warm) {
  card(s, x, y, w, h, warm ? "F6E8D8" : "E3ECF3");
  tx(s, text, { x: x + 0.3, y, w: w - 0.6, h, fontSize: 16, color: C.text1, valign: "middle" });
}
const B = (t) => ({ text: t, options: { bold: true } });
const P = (t) => ({ text: t });
function bullets(items, extra) {
  return items.map((t, i) => ({ text: t, options: Object.assign({ bullet: true, breakLine: i < items.length - 1 }, extra || {}) }));
}
function table(s, rows, o) {
  const head = rows[0].map((t) => ({ text: t, options: { bold: true, color: C.text1, fill: { color: C.background2 } } }));
  const body = rows.slice(1).map((r) => r.map((t) => ({ text: String(t) })));
  s.addTable([head, ...body], Object.assign({ fontSize: 14, color: C.text2, border: { type: "solid", pt: 0.75, color: "C9CFD2" }, margin: [0.06, 0.1, 0.06, 0.1], valign: "middle" }, o));
}

// ================= 1. cover =================
pres.addSection({ title: "연구 질문과 전체 흐름" });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "연구 질문과 전체 흐름" });
  s._title = "표지";
  s.addText("연구 진행 보고 · 2026-11-16", { placeholder: "eyebrow" });
  s.addText("IBD 보험가이드북\nRAG 기능 추가 평가", { placeholder: "title" });
  s.addText("같은 AI에 2024 대한장연구학회 보험가이드북 발췌를 붙이면 국내 급여 기준 답이 얼마나 정확해지는가. gpt-5.6-terra로 재고, 상위 모델 Claude Opus 5.5와 공개 모델 Qwen3-14B로 다시 확인했다.", { placeholder: "body" });
  tx(s, "보고 점수는 답 1회 · 채점 1회분이며, 임상의 검증 전이다.", { x: 0.8, y: 5.9, w: 11, h: 0.4, fontSize: 13, color: C.accent6 });
  addNote(s);
}

// ================= 1b. key findings =================
{
  const s = content("요약", "핵심 발견 다섯 가지", "연구 질문과 전체 흐름");
  const ks = [
    ["01 · 정확도", "네 유형 모두 RAG 추가가 높았다. A 0.44 → 0.81 · A2 0.09 → 0.91 · C 0.81 → 0.93 · D 0.32 → 0.43 (gpt-5.6-terra)", null],
    ["02 · 기본 AI의 오류", "다른 기준을 섞었다. A형 ‘이전 치료’ 오답 10개 모두 TNF 억제제를 언급, 국내 급여가 아닌 해외 약 3건 추천", null],
    ["03 · RAG 추가의 오류", "D형은 검색(빠뜨린 약 43건 모두 그 약의 쪽을 못 가져옴), A형은 답변(조건을 덜 옮긴 축약 16건)", null],
    ["04 · 안전", [B("안전 관련 오답은 RAG 추가가 더 많았다"), P(" (C 5 대 1, D 6 대 3문항). 원인은 체크리스트 쪽 미검색 하나, 규칙 A로 근거가 모두 들어온다")], "F6E8D8"],
    ["05 · 다른 모델 · 11.16", [B("결론은 같고 틀리는 방식은 달랐다. "), P("A형 Opus 5.5 0.47 → 0.91, 공개 모델 Qwen3-14B 0.08 → 0.63. 같은 발췌의 D형 안전 오답 6건은 세 모델 모두 같았다")], "E3ECF3"],
    ["06 · 보고 범위", "모든 점수는 답 1회 · 채점 1회이며 임상의 검증 전이다. 결과를 본 뒤 정한 분석은 사후 분석으로 보고한다", null],
  ];
  const w = 3.877;
  ks.forEach(([lab, body, fill], i) => {
    const x = 0.6 + (i % 3) * (w + 0.25), y = 1.75 + Math.floor(i / 3) * 2.55;
    card(s, x, y, w, 2.35, fill);
    label(s, lab, x + 0.28, y + 0.22, w - 0.56, fill === "F6E8D8" ? C.accent4 : C.accent1);
    tx(s, body, { x: x + 0.28, y: y + 0.62, w: w - 0.56, h: 1.65, fontSize: 14 });
  });
  addNote(s);
}

// ================= 2. question =================
{
  const s = content("연구 질문", "가이드북을 붙이면 무엇이 달라지는가", "연구 질문과 전체 흐름");
  const qs = [
    ["01 · 정확도", "같은 LLM에 2024 대한장연구학회(KASID) 보험가이드북 발췌만 붙이면, 국내 급여 기준 답의 정확도가 얼마나 오르는가?"],
    ["02 · 어디서", "어떤 기준(나이·활성도·이전 치료·유지·고령·검사 하한)과 어떤 과제(단답·추가 규칙·환자 판정·약제 선택)에서 차이가 큰가?"],
    ["03 · 왜 틀리나", [P("남은 오류는 가이드북을 찾는 "), B("검색 단계"), P("와 읽고 답하는 "), B("답변 단계"), P(" 중 어디에서 생기는가?")]],
    ["04 · 무엇과 헷갈리나", "AI가 틀릴 때 외국·예전 기준을 적용하는가? 보기 없이 물으면 국내 급여가 아닌 약을 추천하는가?"],
  ];
  qs.forEach(([lab, body], i) => {
    const x = 0.6 + (i % 2) * 6.19, y = 1.75 + Math.floor(i / 2) * 2.55;
    card(s, x, y, 5.94, 2.3);
    label(s, lab, x + 0.3, y + 0.28, 5.3);
    tx(s, body, { x: x + 0.3, y: y + 0.72, w: 5.3, h: 1.4, fontSize: 16 });
  });
  addNote(s);
}

// ================= 2b. glossary =================
{
  const s = content("용어 풀이", "처음 듣는 분을 위한 용어 정리", "연구 질문과 전체 흐름");
  table(s, [
    ["용어", "이 발표에서의 뜻"],
    ["급여 기준 · 보험가이드북", "건강보험이 약값을 내 주는 조건(나이·활성도·이전 치료 등). 가이드북에 약마다 정리"],
    ["기본 AI", "답하는 모델(gpt-5.6-terra, 11.16엔 Claude Opus 5.5·Qwen3-14B)이 자료 없이 기억만으로 답함"],
    ["RAG 추가", "같은 모델이 질문에 맞는 가이드북 5쪽을 찾아 읽고 답함 (RAG = 검색 + 답)"],
    ["고시 쪽 · 체크리스트 쪽", "약별 급여 기준이 적힌 쪽 · 투여 전 검사 수치 하한(Hb·ANC·ALC)이 적힌 쪽"],
    ["LLM 채점자", "다른 AI(gpt-6-sol)가 정답·원문을 보고 서술형 답을 맞음·부분·틀림으로 판정"],
    ["점수 (0~1)", "맞음 1 · 부분 0.5 · 틀림 0의 평균. 0.80 = 100문항 중 80문항 맞힌 셈"],
    ["재현율 · 정밀도 (D형)", "정답 약 중 몇 개를 썼나 · 쓴 약 중 몇 개가 정답인가"],
    ["신뢰구간 · κ", "점수 차이가 우연이 아님을 보이는 범위 · 사람과 AI 판정이 얼마나 일치하는지"],
    ["사후 분석", "결과를 본 뒤 정한 분석. 확정 결론이 아니라 가설로 보고"],
    ["배치 API", "요청을 모아 한꺼번에 보내고 나중에 받는 방식. 요금 절반, 모델·설정·결과는 일반 호출과 같음"],
  ], { x: 0.6, y: 1.7, w: 12.13, colW: [3.2, 8.93], fontSize: 14, rowH: 0.44 });
  addNote(s);
}

// ================= 3. flow =================
{
  const s = content("전체 흐름", "문항은 코드가 만들고, 두 대상에 묻고, 채점했다", "연구 질문과 전체 흐름");
  const steps = [
    ["가이드북 → CSV", "2024 KASID 보험가이드북 Ver.3(PDF)의 약제별 급여 기준을 CSV 44행으로 옮김"],
    ["문항 380개 생성", "코드가 CSV에서 질문과 정답을 뽑음. A 107 · A2 38 · C 198 · D 37. LLM은 쓰지 않음"],
    ["검수", "자동 점검(중복·정답 노출·재현성) + 연구자 1차 검수. 임상의 검수는 아직"],
    ["두 대상에 질문", "같은 모델(gpt-5.6-terra)을 가이드북 없이(기본 AI) / 발췌 5쪽과 함께(RAG 추가)"],
    ["채점", "A·A2형은 LLM 채점자(gpt-6-sol), C·D형은 코드가 정답과 비교"],
    ["분석 · 검증", "채점자 편향 점검, 오답 원인 분류, 검색 시뮬레이션, 인용문 원문 대조, 오답 위험도 (API 없이)"],
  ];
  const w = 3.877;
  steps.forEach(([t, b], i) => {
    const x = 0.6 + (i % 3) * (w + 0.25), y = 1.75 + Math.floor(i / 3) * 2.55;
    card(s, x, y, w, 2.3);
    tx(s, String(i + 1).padStart(2, "0"), { x: x + 0.28, y: y + 0.22, w: 1, h: 0.45, fontSize: 24, bold: true, color: C.accent1, fontFace: "Arial" });
    tx(s, t, { x: x + 0.28, y: y + 0.72, w: w - 0.56, h: 0.4, fontSize: 17, bold: true, color: C.text1 });
    tx(s, b, { x: x + 0.28, y: y + 1.15, w: w - 0.56, h: 1.05, fontSize: 14 });
  });
  addNote(s);
}

// ================= 3b. timeline =================
{
  const s = content("진행 기록", "3주 동안 이렇게 진행했다", "연구 질문과 전체 흐름");
  const ev = [
    ["10.26–27", "기반 구축", "가이드북 CSV 44행과 검색용 조각 70개, RAG 앱(백엔드·화면), A형 107문항. A형 첫 실행과 v1 채점"],
    ["11.09–10", "채점 다시 세움", "v1 판정을 Claude가 검토(사람 판정 아님) → 원문 쪽을 주는 v2 → 규칙 3개를 더한 v2.1 확정, 3회 반복 채점"],
    ["11.11", "문항 확장", "A2 38 · C 198 · D 37문항 생성. CSV ↔ PDF 원문 대조 검수표"],
    ["11.12", "A형 수정", "질문을 고친 24문항은 답을 다시 받고, 열쇠만 고친 7문항은 다시 채점. 옛 결과는 superseded 파일로 보존"],
    ["11.13", "실행 · 1차 검수", "A2·C·D형 두 대상 실행. 연구자 1차 검수(결정 20개), C형 SC 22문항 재질문, 임상의 검수표"],
    ["11.14–15", "분석 · 정리", "채점자 편향 점검, 오답 원인 분류, 검색 시뮬레이션, 민감도, 인용문 원문 대조, 오답 위험도. 코드 정리·재현 확인, 임상의 배포용 검수표"],
    ["11.16", "다른 모델 확인", "Claude Opus 5.5(배치 API)·Qwen3-14B(GPU 서버)로 네 유형 760답씩, A·A2형 gpt-6-sol 채점(배치). 같은 발췌로 세 모델 비교"],
  ];
  const X = 0.6, W = 12.13;
  n += 1;
  s.addShape(SH.LINE, { x: X + 1.55, y: 1.85, w: 0, h: 4.75, line: { color: C.accent6, width: 2 }, objectName: `tl-line-${n}` });
  ev.forEach(([d, t, b], i) => {
    const y = 1.75 + i * 0.7;
    tx(s, d, { x: X, y: y + 0.05, w: 1.35, h: 0.4, fontSize: 15, bold: true, color: C.accent1, fontFace: "Arial", align: "right" });
    n += 1;
    s.addShape(SH.OVAL, { x: X + 1.47, y: y + 0.12, w: 0.17, h: 0.17, fill: { color: C.accent1 }, line: { color: C.background1, width: 1.5 }, objectName: `tl-dot-${n}` });
    tx(s, t, { x: X + 1.85, y: y + 0.05, w: 2.0, h: 0.4, fontSize: 15, bold: true, color: C.text1 });
    tx(s, b, { x: X + 3.9, y: y + 0.05, w: W - 3.9, h: 0.62, fontSize: 13 });
  });
  addNote(s);
}

// ================= 4. items =================
pres.addSection({ title: "문항을 어떻게 만들고 검수했나" });
{
  const s = content("문항 · 380개", "네 가지 유형으로 단답부터 약제 선택까지 묻는다", "문항을 어떻게 만들고 검수했나");
  table(s, [
    ["유형", "문항", "질문 예시 → 정답", "정답 · 채점"],
    ["A · 급여 기준 단답", "107", "[Infliximab IV, 성인 크론병] 급여 활성도 기준은? → CDAI 220 이상", "CSV에서 코드 · LLM 채점"],
    ["A2 · 추가 급여 규칙", "38", "재투여·처방 기간·용량 증량·교체투여 등. 예: 1회 처방 기간 한도는?", "CSV 메모에서 코드 · LLM 채점"],
    ["C · 환자 사례 판정", "198", "45세 남성, CDAI 220, 스테로이드·아자티오프린 무반응 … 급여 대상인가? → 예 / 아니오 / 판단 불가", "코드 판정 · 코드 채점"],
    ["D · 약제 선택", "37", "보기 없이 “급여되는 생물학제제·소분자제제를 모두 쓰시오” → 성분명 목록", "9개 성분 대입 · 코드 채점"],
  ], { x: 0.6, y: 1.75, w: 12.13, colW: [2.5, 1.0, 5.83, 2.8], fontSize: 15, rowH: [0.5, 0.75, 0.75, 0.95, 0.75] });
  tx(s, "A형 본 점수는 101문항(금기 6문항은 보조). 질문에는 쪽 번호를 넣지 않았다(검색 대상 본문에 쪽 번호가 있어 RAG 추가만 유리해지므로).", { x: 0.6, y: 5.9, w: 12.1, h: 0.7, fontSize: 13, color: C.accent3 });
  addNote(s);
}

// ================= 5. cases =================
{
  const s = content("C · D형 사례 설계", "기본 환자에서 조건을 하나씩 깨서 만들었다", "문항을 어떻게 만들고 검수했나");
  tx(s, "C형 · 198문항 (예 83 / 아니오 88 / 판단 불가 27)", { x: 0.6, y: 1.7, w: 7.2, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  table(s, [
    ["사례 유형", "문항", "정답"],
    ["기본 (모든 조건 충족, 경계값)", "25", "예"],
    ["활성도 경계 미달 (CDAI 219)", "21", "아니오"],
    ["활성도 점수 미제시", "21", "판단 불가"],
    ["이전 치료 부족 / 내약성 없음", "25 / 23", "아니오 / 예"],
    ["고령·고위험 (68세 등)", "11", "예 7 / 아니오 4"],
    ["검사 하한 (Hb·ANC·ALC)", "15", "예 3 / 아니오 12"],
    ["유지 인정 / 불인정 / 미제시", "25 / 25 / 6", "예 / 아니오 / 판단 불가"],
  ], { x: 0.6, y: 2.2, w: 7.2, colW: [3.6, 1.4, 2.2], fontSize: 14, rowH: 0.5 });
  card(s, 8.1, 1.7, 4.63, 4.95);
  label(s, "D형 · 37문항, 보기 없음", 8.4, 1.95, 4.1);
  tx(s, bullets([
    "정답: 환자를 가이드북 9개 성분에 하나씩 대입해 코드가 계산",
    "함정 11: 68세는 JAK만 제외, Hb 8.5는 Tofacitinib만 제외, 장형 베체트 18세, 누공성 크론병은 Infliximab만",
    "TNF 실패 사례(5)는 실패한 Adalimumab을 정답에서 뺌",
    "해외 약(Risankizumab 등)과 실패한 약 재사용은 따로 센다",
  ], { paraSpaceAfter: 8 }), { x: 8.4, y: 2.4, w: 4.1, h: 4.1, fontSize: 15 });
  addNote(s);
}

// ================= 6. review =================
{
  const s = content("검수", "임상의 검수만 남았다", "문항을 어떻게 만들고 검수했나");
  const cols = [
    ["자동 점검 · 코드", ["재현성: 다시 생성해도 같음", "중복·정답 누락·정답 노출·쪽 번호 모두 0", "C형 ↔ D형 코드 교차 계산 불일치 0", "CSV 숫자 ↔ PDF 원문 대조"], C.accent1, null],
    ["연구자 1차 검수 · 11-13", ["해석이 필요했던 결정 20개: 동의 19, 수정 1(SC 사례 문구)", "표본 114문항(A 24 · A2 10 · C 43 · D 37) 모두 적합", "문구를 고친 C형 SC 22문항은 답을 다시 받음"], C.accent1, null],
    ["임상의 2인 검수 · 0건", ["검수표 준비됨: 문항 380행 + 결정 20행, 노란 칸만 작성", "모델 답은 빼서 판정에 영향이 없게 함"], C.accent4, "F6E8D8"],
  ];
  const w = 3.877;
  cols.forEach(([t, items, col, fill], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 2.75, fill);
    label(s, t, x + 0.28, 1.98, w - 0.56, col);
    tx(s, bullets(items, { paraSpaceAfter: 6 }), { x: x + 0.28, y: 2.42, w: w - 0.56, h: 2.0, fontSize: 14 });
  });
  callout(s, "가이드북 자체 문제 2건 발견: Ozanimod 평가 시점이 쪽마다 다름(10~20주 vs 10~22주), Filgotinib 체크리스트의 ‘절대 림프구수(ANC)’ 오기", 0.6, 4.8, 12.13, 0.95, true);
  addNote(s);
}

// ================= 7. arms =================
pres.addSection({ title: "무엇을 비교하고 어떻게 채점했나" });
{
  const s = content("비교 대상", "같은 모델, 발췌가 있느냐 하나만 다르다", "무엇을 비교하고 어떻게 채점했나");
  const arms = [
    ["기본 AI", "gpt-5.6-terra, 기억만으로", ["근거 문서 없음", "시스템 지시·질문 앞·답 형식 세 곳에서 “2024 대한장연구학회 보험가이드북 기준으로만 답하라”"], C.accent4, "F6E8D8"],
    ["RAG 추가", "gpt-5.6-terra + 가이드북 발췌 5쪽", ["검색으로 고른 상위 5쪽을 질문과 함께 줌", "“근거는 제공된 발췌뿐. 발췌에 없는 수치·조건·금기는 만들지 말 것”"], C.accent1, "E3ECF3"],
  ];
  arms.forEach(([t, sub, items, col, fill], i) => {
    const x = 0.6 + i * 6.19;
    card(s, x, 1.75, 5.94, 2.75, fill);
    label(s, t, x + 0.3, 1.98, 5.3, col);
    tx(s, sub, { x: x + 0.3, y: 2.35, w: 5.3, h: 0.42, fontSize: 18, bold: true, color: C.text1 });
    tx(s, bullets(items, { paraSpaceAfter: 6 }), { x: x + 0.3, y: 2.9, w: 5.3, h: 1.5, fontSize: 15 });
  });
  table(s, [
    ["답 형식 (두 대상 같음)", "A · A2형", "C형", "D형"],
    ["첫 줄", "답: …", "판정: 예 / 아니오 / 판단 불가", "인정: 성분명, …"],
    ["둘째 줄", "(없음)", "이유: 한두 문장", "이유: 한두 문장"],
  ], { x: 0.6, y: 4.85, w: 12.13, colW: [3.0, 2.5, 3.6, 3.03], fontSize: 14, rowH: 0.45 });
  addNote(s);
}

// ================= 8. rag =================
{
  const s = content("방법 · RAG 추가", "RAG 기능은 이렇게 추가했다: 가이드북 검색 → 5쪽을 질문과 함께", "무엇을 비교하고 어떻게 채점했나");
  function box(x, y, w, h, t, sub, hi) {
    n += 1;
    s.addShape(SH.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: hi ? "E3ECF3" : C.background2 }, line: { color: hi ? HEX.accent1 : "C9CFD2", width: 1.25 }, rectRadius: 0.08, objectName: `box-${n}` });
    tx(s, [{ text: t, options: { bold: true, color: C.text1, fontSize: 14, breakLine: true } }, { text: sub, options: { fontSize: 12 } }], { x: x + 0.1, y, w: w - 0.2, h, valign: "middle", align: "center" });
  }
  function arrow(x, y) { n += 1; s.addShape(SH.RIGHT_ARROW, { x, y, w: 0.32, h: 0.26, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: `arrow-${n}` }); }
  // ① 준비 (한 번)
  label(s, "① 준비 · 한 번만", 0.6, 1.62, 4);
  let x = 0.6; const y1 = 1.98, h1 = 0.95;
  box(x, y1, 2.6, h1, "보험가이드북 PDF", "2024 KASID Ver.3"); x += 2.6 + 0.08; arrow(x, y1 + 0.35); x += 0.32 + 0.08;
  box(x, y1, 3.0, h1, "쪽 단위 70조각", "쪽·장·제목·약제·질환 표시"); x += 3.0 + 0.08; arrow(x, y1 + 0.35); x += 0.32 + 0.08;
  box(x, y1, 2.55, h1, "키워드 색인 (BM25)", "한글 2글자 조각까지"); x += 2.55 + 0.12;
  box(x, y1, 12.73 - x, h1, "의미 색인 (임베딩)", "text-embedding-3-large");
  // ② 질문마다
  label(s, "② 질문마다 · 검색", 0.6, 3.1, 4);
  x = 0.6; const y2 = 3.46, h2 = 0.95;
  box(x, y2, 1.55, h2, "질문", "원문 그대로"); x += 1.55 + 0.08; arrow(x, y2 + 0.35); x += 0.32 + 0.08;
  box(x, y2, 2.35, h2, "후보 모으기", "키워드 12쪽 + 의미 12쪽"); x += 2.35 + 0.08; arrow(x, y2 + 0.35); x += 0.32 + 0.08;
  box(x, y2, 2.1, h2, "RRF로 합침", "최대 20쪽"); x += 2.1 + 0.08; arrow(x, y2 + 0.35); x += 0.32 + 0.08;
  box(x, y2, 2.35, h2, "재랭커로 다시 정렬", "bge-reranker-v2-m3"); x += 2.35 + 0.08; arrow(x, y2 + 0.35); x += 0.32 + 0.08;
  box(x, y2, 12.73 - x, h2, "상위 5쪽", "질문과 가장 맞는 쪽", true);
  // ③ 같은 AI에 넣는 입력 비교
  label(s, "③ 같은 AI에 넣는 입력 · 다른 것은 발췌 5쪽 하나", 0.6, 4.58, 8);
  card(s, 0.6, 4.94, 5.94, 1.88);
  tx(s, [B("기본 AI"), { text: "\n지시: 2024 보험가이드북 기준으로만 답하라\n문제: (질문)\n답 형식: 답: … / 판정: … / 인정: …", options: { fontSize: 12, fontFace: "Consolas" } }],
    { x: 0.85, y: 5.0, w: 5.5, h: 1.75, fontSize: 13 });
  card(s, 6.79, 4.94, 5.94, 1.88, "E3ECF3");
  tx(s, [B("기본 AI + RAG 추가"), { text: "\n지시: 근거는 제공된 발췌뿐, 발췌에 없는 수치·조건은 만들지 말 것\n[1] p.48 · 약제 Filgotinib · 질환 UC · (원문)  … [5]\n문제: (질문)   답 형식: 같음", options: { fontSize: 12, fontFace: "Consolas" } }],
    { x: 7.04, y: 5.0, w: 5.5, h: 1.75, fontSize: 13 });
  addNote(s);
}

// ================= 9. grading =================
{
  const s = content("채점", "A·A2형은 LLM 채점자, C·D형은 코드가 채점했다", "무엇을 비교하고 어떻게 채점했나");
  card(s, 0.6, 1.75, 6.6, 3.0);
  label(s, "LLM 채점자 · gpt-6-sol · 규칙 v2.1", 0.9, 1.98, 6.0);
  tx(s, [
    B("받는 것: "), P("질문, 정답, 채점 열쇠, 가이드북 원문 쪽, 척도 범위, 채점할 답. 답이 어느 대상의 것인지는 모른다"), { text: "", options: { breakLine: true } },
    B("규칙 예: "), P("뜻이 같으면 맞음 · 숫자·이상/초과가 다르면 그 요소 틀림 · 원문에 없는 덧붙임은 틀림 · 이전 치료는 3요소 · 평가 시점만 틀리면 부분"), { text: "", options: { breakLine: true } },
    B("점수: "), P("맞음 1, 부분 0.5, 틀림 0의 평균"),
  ], { x: 0.9, y: 2.42, w: 6.0, h: 2.2, fontSize: 15, paraSpaceAfter: 10 });
  card(s, 7.45, 1.75, 5.28, 3.0);
  label(s, "코드 채점 · API 없음", 7.75, 1.98, 4.7);
  tx(s, [
    B("C형: "), P("‘판정:’ 줄을 정답과 비교. 못 읽으면 형식 오류(이번 0건)"), { text: "", options: { breakLine: true } },
    B("D형: "), P("‘인정:’ 줄의 약 집합을 정답 집합과 비교. 완전 일치, 재현율, 정밀도"), { text: "", options: { breakLine: true } },
    P("해외·가이드북 밖 약, 이미 실패한 약 재사용은 따로 센다"),
  ], { x: 7.75, y: 2.42, w: 4.7, h: 2.2, fontSize: 15, paraSpaceAfter: 10 });
  tx(s, "보고 점수는 답 1회 · 채점 1회분. 반복 채점 현황은 다음 장, 답 반복 측정은 다음 단계에서 한다.", { x: 0.6, y: 5.0, w: 12.1, h: 0.4, fontSize: 13, color: C.accent3 });
  addNote(s);
}

// ================= 9b. grading history =================
{
  const s = content("채점 규칙의 변천", "채점 방식은 세 번 다듬었고, 최종은 v2.1이다", "무엇을 비교하고 어떻게 채점했나");
  const vs = [
    ["v1 · 10.27", "정답·채점 열쇠·답만 주고 채점", ["원문을 못 봐서 맞는 덧붙임도 틀림 처리", "Claude가 판정을 검토해 기본 AI 9건 · RAG 추가 13건을 바꿈 (사람 판정 아님, 기준 정답으로 쓰지 않음)"], null],
    ["v2 · 11.10", "원문 쪽과 척도 범위를 함께 줌", ["덧붙인 내용을 ‘원문에 있음 / 없음’으로 따로 기록 → 감점 이유를 나중에 확인 가능", "같은 답을 3번 채점해 채점자 자체 일관성 측정"], null],
    ["v2.1 · 11.10 확정", "연구자가 정한 규칙 3개를 더함 · 주 결과", ["평가 시점만 틀리면 부분", "‘N 미만이면 투여 불가’처럼 결과를 밝힌 여집합 표현은 맞음", "‘함께 써도 정답’은 있든 없든 감점 없음"], "E3ECF3"],
  ];
  const w = 3.877;
  vs.forEach(([t, sub, items, fill], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 2.65, fill);
    label(s, t, x + 0.28, 1.95, w - 0.56);
    tx(s, sub, { x: x + 0.28, y: 2.32, w: w - 0.56, h: 0.6, fontSize: 15, bold: true, color: C.text1 });
    tx(s, bullets(items, { paraSpaceAfter: 5 }), { x: x + 0.28, y: 2.95, w: w - 0.56, h: 1.8, fontSize: 13 });
  });
  table(s, [
    ["v2.1 점검 (A형 본 점수)", "기본 AI", "RAG 추가"],
    ["v1 + Claude 검토와 일치 (11.10 시점)", "0.980 · κ 0.968", "0.990 · κ 0.977"],
    ["3회 채점이 모두 같은 판정 (지금, 74문항)", "71 / 74", "74 / 74"],
    ["점수: 1회분 → 3회 다수결", "0.441 → 0.436", "0.807 → 0.807"],
  ], { x: 0.6, y: 4.65, w: 8.3, colW: [4.1, 2.1, 2.1], fontSize: 13, rowH: 0.4 });
  tx(s, "11.12에 고친 A형 27문항(본 점수 기준)과 A2형 38문항은 아직 채점 1회뿐이다. 반복 측정 때 함께 맞춘다.", { x: 9.15, y: 4.65, w: 3.58, h: 1.6, fontSize: 13, color: C.accent4, valign: "middle" });
  addNote(s);
}

// ================= 9c. walkthrough A2 =================
function walk(s, q, left, right, bottom) {
  card(s, 0.6, 1.7, 12.13, 1.05);
  label(s, q[0], 0.9, 1.82, 11.5);
  tx(s, q[1], { x: 0.9, y: 2.15, w: 11.5, h: 0.55, fontSize: 15, color: C.text1 });
  [left, right].forEach(([lab, ans, verdict, fill, col], i) => {
    const x = 0.6 + i * 6.19;
    card(s, x, 2.95, 5.94, 2.6, fill);
    label(s, lab, x + 0.3, 3.1, 5.3, col);
    tx(s, ans, { x: x + 0.3, y: 3.5, w: 5.34, h: 1.15, fontSize: 15, color: C.text1 });
    tx(s, verdict, { x: x + 0.3, y: 4.65, w: 5.34, h: 0.85, fontSize: 13 });
  });
  callout(s, bottom, 0.6, 5.75, 12.13, 0.95);
}
{
  const s = content("한 문항 따라가기 ① · A2형 · LLM 채점", "처방 기간을 물으면: 기본 AI는 지어내고, RAG 추가는 옮겨 온다", "무엇을 비교하고 어떻게 채점했나");
  walk(s,
    ["질문 · A2-GEN-P2 (재투여 가이드)", "재투여 가이드의 점검 항목에 적힌 최대 처방량(1회 처방 기간)은? 더 길게 처방할 수 있는 조건이 있다면 무엇인가?"],
    ["기본 AI · 자료 없음", "답: 최대 8주, 환자 상태가 안정적인 경우 최대 16주까지 처방 가능",
      [B("채점: 틀림 (0점). "), P("세 요소 모두 다름. ‘8주’ ‘16주’는 원문에 없는 덧붙임으로 기록")], "F6E8D8", C.accent4],
    ["RAG 추가 · 가져온 쪽 p.59 · 58 · 44 · 45 · 28", "답: 최대 1개월. 최초 투여일로부터 6개월 이후 안정된 질병 활성도를 보이고 부작용이 없는 환자는 최대 2~3개월 처방 가능",
      [B("채점: 맞음 (1점). "), P("필수 요소 3개 모두 맞음. p.59(심평원 재투여 가이드) 문장을 그대로 옮김")], "E3ECF3", C.accent1],
    [B("정답과 채점 열쇠는 코드가 CSV에서 만들었다: "), P("‘최대 1개월’ · ‘6개월 이후 안정·부작용 없음’ · ‘최대 2~3개월’ 세 요소를 채점자가 하나씩 확인한다")]);
  addNote(s);
}

// ================= 10. results =================
pres.addSection({ title: "결과" });
{
  const s = content("결과 · 한눈에 · gpt-5.6-terra", "네 유형 모두 RAG 추가가 높았다", "결과");
  // 범례
  s.addShape(SH.RECTANGLE, { x: 4.0, y: 1.75, w: 0.22, h: 0.22, fill: { color: C.accent2 }, line: { color: C.accent2 }, objectName: "legend-base" });
  tx(s, "기본 AI (기억만)", { x: 4.3, y: 1.7, w: 2.6, h: 0.32, fontSize: 14 });
  s.addShape(SH.RECTANGLE, { x: 7.0, y: 1.75, w: 0.22, h: 0.22, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "legend-agent" });
  tx(s, "RAG 추가 (발췌 5쪽)", { x: 7.3, y: 1.7, w: 3.2, h: 0.32, fontSize: 14 });
  const rows = [
    ["A형 본 점수", "101문항 · LLM 채점", 0.441, 0.807],
    ["A2형", "38문항 · LLM 채점", 0.092, 0.908],
    ["C형 정답률", "198문항 · 코드 채점", 0.813, 0.934],
    ["D형 완전 일치", "37문항 · 코드 채점", 0.324, 0.432],
  ];
  const X0 = 4.0, MAXW = 7.5, BH = 0.36;
  rows.forEach(([name, sub, b, a], i) => {
    const y = 2.3 + i * 1.08;
    tx(s, name, { x: 0.6, y: y + 0.02, w: 3.2, h: 0.4, fontSize: 18, bold: true, color: C.text1 });
    tx(s, sub, { x: 0.6, y: y + 0.44, w: 3.2, h: 0.32, fontSize: 12, color: C.accent3 });
    [[b, C.accent2, "base"], [a, C.accent1, "agent"]].forEach(([v, col, k], j) => {
      const yy = y + j * (BH + 0.08);
      s.addShape(SH.RECTANGLE, { x: X0, y: yy, w: MAXW * v, h: BH, fill: { color: col }, line: { color: col }, objectName: `bar-${i}-${k}` });
      tx(s, v.toFixed(3), { x: X0 + MAXW * v + 0.12, y: yy, w: 0.9, h: BH, fontSize: 14, bold: true, color: C.text1, valign: "middle" });
    });
  });
  tx(s, "읽는 법: 1.0이 만점. A형 0.441 → 0.807은 101문항 중 약 45문항 → 약 82문항 맞힌 셈(부분은 반 개). 답 1회 · 채점 1회, 임상의 검증 전.", { x: 0.6, y: 6.5, w: 12.1, h: 0.32, fontSize: 12, color: C.accent3 });
  addNote(s);
}

// ================= 11. results-a =================
{
  const s = content("결과 · A형 101문항", "한국 고유 기준에서 차이가 컸다", "결과");
  table(s, [
    ["기준", "문항", "기본 AI", "RAG 추가"],
    ["유지 기준", "25", "0.12", "0.90"],
    ["고령·고위험", "7", "0.14", "1.00"],
    ["나이", "7", "0.29", "1.00"],
    ["이전 치료", "25", "0.30", "0.68"],
    ["활성도", "25", "0.76", "0.80"],
    ["검사 하한", "12", "1.00", "0.67"],
  ], { x: 0.6, y: 1.75, w: 6.9, colW: [2.4, 1.2, 1.65, 1.65], fontSize: 15, rowH: 0.5 });
  tx(s, [B("원래 아는 것: "), P("국제적으로 비슷한 활성도 점수, 허가사항의 검사 하한"), { text: "", options: { breakLine: true } }, B("모르는 것: "), P("한국 고유의 유지 기준·이전 치료 조건·고령 조항")], { x: 0.6, y: 5.45, w: 6.9, h: 1.0, fontSize: 14 });
  card(s, 7.8, 1.75, 4.93, 4.7, "E3ECF3");
  label(s, "점수 차이 (RAG 추가 − 기본 AI)", 8.1, 2.0, 4.4);
  tx(s, "+0.366", { x: 8.1, y: 2.45, w: 4.4, h: 0.95, fontSize: 54, bold: true, color: C.accent1, fontFace: "Arial" });
  tx(s, bullets(["0.441 → 0.807", "95% 부트스트랩 CI +0.27 ~ +0.47", "내용 묶음 30개 단위 CI +0.18 ~ +0.55", "개선 51 / 악화 5, 부호검정 p = 1×10⁻¹⁰"], { paraSpaceAfter: 6 }), { x: 8.1, y: 3.6, w: 4.4, h: 2.7, fontSize: 15 });
  addNote(s);
}

// ================= 12. results-cd =================
{
  const s = content("결과 · C형과 D형", "사례 판정은 좋아졌고, 여러 약 고르기는 여전히 어렵다", "결과");
  card(s, 0.6, 1.75, 5.94, 4.85);
  label(s, "C형 · 환자 사례 판정 198", 0.9, 1.98, 5.3);
  table(s, [["지표", "기본 AI", "RAG 추가"], ["정답률", "0.813", "0.934"], ["정답 ‘예’ 83문항", "0.70", "0.95"], ["함정 18문항", "0.50", "1.00"], ["검사 하한 15문항", "0.80", "0.67"]],
    { x: 0.9, y: 2.42, w: 5.34, colW: [2.54, 1.4, 1.4], fontSize: 14, rowH: 0.45, fill: { color: C.background1 } });
  tx(s, "기본 AI는 급여 대상 환자를 막는 쪽으로 틀렸다(‘예’를 ‘아니오’로 23건).", { x: 0.9, y: 5.0, w: 5.34, h: 1.0, fontSize: 15 });
  card(s, 6.79, 1.75, 5.94, 4.85);
  label(s, "D형 · 약제 선택 37 (보기 없음)", 7.09, 1.98, 5.3);
  table(s, [["지표", "기본 AI", "RAG 추가"], ["완전 일치", "0.324", "0.432"], ["재현율", "0.85", "0.75"], ["정밀도", "0.78", "0.88"], ["해외 약 쓴 사례", "3", "0"], ["실패한 약 재사용", "0", "4"]],
    { x: 7.09, y: 2.42, w: 5.34, colW: [2.54, 1.4, 1.4], fontSize: 14, rowH: 0.45, fill: { color: C.background1 } });
  tx(s, "RAG 추가는 틀린 약은 덜 넣지만 정답 약을 빠뜨린다(Vedolizumab 19회).", { x: 7.09, y: 5.45, w: 5.34, h: 1.0, fontSize: 15 });
  addNote(s);
}

// ================= 13. confusion =================
{
  const s = content("결과 · 기본 AI의 오류 (탐색적 발견)", "기본 AI는 다른 기준을 섞었다", "결과");
  const stats = [
    ["10/10", [P("A형 ‘이전 치료’ 오답이 모두 TNF 억제제를 언급. 6개는 TNF 실패를 "), B("필수로 요구")]],
    ["11/23", "C형에서 급여 대상 환자를 막은 23문항 중 11문항이 TNF·생물학제제 실패를 이유로 듦"],
    ["3건", "D형에서 국내 급여가 아닌 Risankizumab(해외 허가 IL-23 억제제)을 추천"],
  ];
  const w = 3.877;
  stats.forEach(([num, body], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 2.6, "F6E8D8");
    tx(s, num, { x: x + 0.28, y: 1.95, w: w - 0.56, h: 0.85, fontSize: 44, bold: true, color: C.accent4, fontFace: "Arial" });
    tx(s, body, { x: x + 0.28, y: 2.85, w: w - 0.56, h: 1.4, fontSize: 14 });
  });
  tx(s, "가능한 원인", { x: 0.6, y: 4.65, w: 6, h: 0.4, fontSize: 17, bold: true, color: C.text1 });
  tx(s, bullets(["미국 허가사항 (JAK 억제제는 TNF 실패 후)", "예전 한국 기준 (Vedolizumab은 2017~2020.7 TNF 실패 후 2차 급여)", "일반 통념"], { paraSpaceAfter: 4 }), { x: 0.6, y: 5.1, w: 6.4, h: 1.5, fontSize: 15 });
  callout(s, "한국 가이드북을 검색하는 RAG 추가에서는 거의 사라졌다: 해외 약 0건, C형 함정 18문항 1.00.", 7.3, 4.75, 5.43, 1.3);
  addNote(s);
}

// ================= 14. bias =================
pres.addSection({ title: "채점자 점검과 오류 분석" });
{
  const s = content("검증 · LLM 채점자", "채점자가 한쪽으로 치우친 증거는 없었다", "채점자 점검과 오류 분석");
  tx(s, "확인한 것 (API 없이 저장된 채점 결과로)", { x: 0.6, y: 1.7, w: 5.9, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  tx(s, bullets(["채점자는 답의 출처를 모른다", "두 대상의 답이 같은 8문항은 판정도 8개 모두 같음", "엄격한 판정(‘반응 감소 시’ 재진술 요구)은 양쪽 모두에 걸림", "연구자 대조와 거의 같음 (A2 RAG 추가 맞음 31 vs 32)", "LLM을 쓰지 않은 C·D형도 같은 방향"], { paraSpaceAfter: 6 }), { x: 0.6, y: 2.2, w: 5.9, h: 3.0, fontSize: 15 });
  tx(s, "민감도: ‘원문에 없는 덧붙임은 틀림’ 규칙", { x: 6.8, y: 1.7, w: 5.93, h: 0.4, fontSize: 16, bold: true, color: C.text1 });
  table(s, [["차이", "원래", "(a) 좁게", "(b) 넓게"], ["A 본 점수", "+0.366", "+0.366", "+0.297"], ["A2", "+0.816", "+0.763", "+0.711"]],
    { x: 6.8, y: 2.2, w: 5.93, colW: [1.73, 1.4, 1.4, 1.4], fontSize: 15, rowH: 0.48 });
  tx(s, "(a) 덧붙임 때문에만 틀린 답을 맞음으로 · (b) 덧붙임이 있는 모든 답을 요소만으로 다시 판정. (b)는 ‘TNF 실패 필요’ 같은 오답까지 살리는 과대 상한이다.", { x: 6.8, y: 3.8, w: 5.93, h: 1.3, fontSize: 13, color: C.accent3 });
  callout(s, "남은 우려: 원문 문체를 옮긴 RAG 추가 답이 유리할 가능성, 채점자가 OpenAI 모델 하나(11.16 Claude·Qwen 답에서도 RAG 추가 우위는 같음), 사람과의 일치도(κ) 없음.", 0.6, 5.45, 12.13, 0.95, true);
  addNote(s);
}

// ================= 15. err-method =================
{
  const s = content("오류 분석 · 방법", "RAG 검색이 가져온 5쪽을 ‘핵심 쪽’과 대조했다", "채점자 점검과 오류 분석");
  const steps = [
    ["가져온 5쪽", "답 파일에 문항마다 저장된 검색 결과(쪽 번호) 그대로"],
    ["문항별 핵심 쪽", bullets(["급여 기준 → 그 약의 고시 쪽", "검사 하한 → 체크리스트 쪽", "처방 기간 → 투약간격 쪽", "D형 → 정답 약마다 고시 쪽"])],
    ["원문과 한 문항씩 대조", "틀린·부분 70문항마다 원인을 붙임: 검색 실패 / 답변 단계(축약·개념 혼동·논리·판단 불가) / 채점"],
  ];
  const w = 3.877;
  steps.forEach(([t, b], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 3.0);
    tx(s, String(i + 1).padStart(2, "0"), { x: x + 0.28, y: 1.97, w: 1, h: 0.45, fontSize: 24, bold: true, color: C.accent1, fontFace: "Arial" });
    tx(s, t, { x: x + 0.28, y: 2.5, w: w - 0.56, h: 0.4, fontSize: 17, bold: true, color: C.text1 });
    tx(s, b, { x: x + 0.28, y: 3.0, w: w - 0.56, h: 1.65, fontSize: 15 });
  });
  tx(s, "API 없음. 분류는 Claude가 했고 임상의 검수 전이다. 코드 analyze_errors.py, 보고서 eval_out/오답원인분류 문서", { x: 0.6, y: 5.0, w: 12.1, h: 0.4, fontSize: 13, color: C.accent3 });
  addNote(s);
}

// ================= 16. err-table =================
{
  const s = content("오류 분석 · 결과 (RAG 추가 오답 70문항)", "D형은 검색에서, A형은 답변에서 틀렸다", "채점자 점검과 오류 분석");
  table(s, [
    ["단계", "원인", "A", "A2", "C", "D"],
    ["검색", "근거 쪽을 못 가져옴", "7", "4", "5", "20문항"],
    ["답변", "문장 축약 (조건 일부만 옮김)", "17", "–", "–", "–"],
    ["답변", "질문 개념 혼동", "5", "–", "–", "–"],
    ["답변", "규칙 적용·논리 오류", "1", "–", "5", "5건"],
    ["답변", "‘판단 불가’ 대신 ‘아니오’", "–", "–", "3", "–"],
    ["채점", "질문 조건 재진술 요구", "–", "2", "–", "–"],
  ], { x: 0.6, y: 1.75, w: 12.13, colW: [1.4, 5.13, 1.4, 1.4, 1.4, 1.4], fontSize: 15, rowH: 0.47 });
  callout(s, [B("D형: "), P("빠뜨린 약 43건 모두 그 약의 고시 쪽을 못 가져왔다 (43/43)")], 0.6, 5.35, 5.94, 1.05);
  callout(s, [B("A형: "), P("쪽은 가져왔는데 ‘내약성 없음·금기’를 빠뜨린 축약 16문항 (−0.079)")], 6.79, 5.35, 5.94, 1.05, true);
  addNote(s);
}

// ================= 17. err-examples =================
{
  const s = content("오류 분석 · 대표 사례", "세 가지 패턴", "채점자 점검과 오류 분석");
  const cards = [
    ["문장 축약 · A형 16문항", C.accent4, "F6E8D8", [
      B("원문: "), P("“…적정한 반응을 나타내지 않거나 "), { text: "내약성이 없는 경우 또는 상기 약제가 금기인", options: { underline: { style: "sng" } } }, P("…”"), { text: "", options: { breakLine: true } },
      B("답: "), P("“…적정한 반응을 나타내지 않은 경우”"), { text: "", options: { breakLine: true } },
      P("근거 쪽은 있었다. 8개 약에서 같은 방식으로 반복된 습관이다."),
    ]],
    ["딸린 쪽 미검색 · A 3 · C 5 · D 6", C.accent1, null, [
      P("Filgotinib 고시 쪽(p.48)은 가져왔지만 Hb·ANC·ALC 하한이 있는 체크리스트(p.49)는 못 가져옴"), { text: "", options: { breakLine: true } },
      P("→ “발췌에는 기준이 없다” → ANC 900 환자를 급여 대상으로 판정"),
    ]],
    ["D형 구조 한계", C.accent1, null, [
      P("정답 약은 사례당 최대 9개인데 검색은 5쪽, 그중 1~2쪽은 비교표"), { text: "", options: { breakLine: true } },
      P("정답 약의 고시 쪽 검색: 63/133 (47%)"), { text: "", options: { breakLine: true } },
      P("Vedolizumab 고시 쪽: 정답에 있는 22문항 중 1문항에서만"),
    ]],
  ];
  const w = 3.877;
  cards.forEach(([t, col, fill, body], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 3.6, fill);
    label(s, t, x + 0.28, 1.98, w - 0.56, col);
    tx(s, body, { x: x + 0.28, y: 2.45, w: w - 0.56, h: 2.8, fontSize: 15, paraSpaceAfter: 12 });
  });
  addNote(s);
}

// ================= 18. simulation =================
{
  const s = content("검색 개선 시뮬레이션 · API 없음", "규칙으로 쪽을 붙이면 근거 쪽은 모두 들어온다", "채점자 점검과 오류 분석");
  card(s, 0.6, 1.75, 4.6, 1.65);
  label(s, "규칙 A · 딸린 쪽", 0.88, 1.95, 4.0);
  tx(s, "가져온 고시 쪽마다 같은 약의 체크리스트·투약간격 쪽을 붙임", { x: 0.88, y: 2.35, w: 4.04, h: 0.95, fontSize: 15 });
  card(s, 0.6, 3.6, 4.6, 1.65);
  label(s, "규칙 B · A + 질문 라우팅", 0.88, 3.8, 4.0);
  tx(s, "질문에 나온 약·질환의 고시 쪽을 붙임. D형은 그 질환의 약 고시 쪽 전부", { x: 0.88, y: 4.2, w: 4.04, h: 0.95, fontSize: 15 });
  table(s, [
    ["항목", "현재", "규칙 A", "규칙 B"],
    ["검색 실패 오답 19건", "0", "14", "19"],
    ["C형 검사 하한 체크리스트", "9/15", "15/15", "15/15"],
    ["D형 정답 약 고시 쪽", "63/133", "63/133", "133/133"],
    ["D형 발췌 크기 (문항당)", "5쪽", "8.9쪽", "14.4쪽"],
    ["A·A2·C형 발췌 크기", "약 5쪽", "약 7쪽", "약 7쪽"],
  ], { x: 5.5, y: 1.75, w: 7.23, colW: [3.03, 1.4, 1.4, 1.4], fontSize: 14, rowH: 0.58 });
  callout(s, "답을 다시 받지 않았다. 근거가 들어온 뒤 실제로 맞히는지는 모른다. 축약·개념 혼동처럼 검색과 무관한 오류는 그대로 남는다.", 0.6, 5.5, 12.13, 0.95, true);
  addNote(s);
}

// ================= 18c. quote check =================
pres.addSection({ title: "추가 분석 · 11.15" });
{
  const s = content("인용문 원문 대조 · API 없음", "RAG 추가는 원문을 옮겨 쓰고, 축약 16건은 코드로 다시 잡힌다", "추가 분석 · 11.15");
  tx(s, "답 글자 중 가이드북 원문과 8자 이상 연속으로 겹치는 비율", { x: 0.6, y: 1.7, w: 6.9, h: 0.4, fontSize: 15, bold: true, color: C.text1 });
  table(s, [
    ["대상", "원문 일치도", "원문 그대로", "일부 바꿔 씀", "자기 말"],
    ["A형 기본 AI", "0.30", "10", "13", "72"],
    ["A형 RAG 추가", "0.70", "49", "33", "11"],
    ["A2형 기본 AI", "0.08", "0", "0", "31"],
    ["A2형 RAG 추가", "0.67", "16", "11", "10"],
  ], { x: 0.6, y: 2.15, w: 6.9, colW: [2.1, 1.35, 1.15, 1.15, 1.15], fontSize: 14, rowH: 0.48 });
  tx(s, "원문 그대로 ≥ 0.8 · 자기 말 < 0.5. ‘적혀 있지 않다’ 답은 표에서 뺐다. RAG 추가가 옮긴 문장은 거의 모두 그 문항에서 검색해 온 5쪽에서 왔다(발췌 일치도 0.70).", { x: 0.6, y: 4.65, w: 6.9, h: 0.9, fontSize: 12, color: C.accent3 });
  card(s, 7.8, 1.7, 4.93, 3.85, "E3ECF3");
  label(s, "조건 누락 (내약성·금기·부작용·중단)", 8.1, 1.92, 4.4);
  tx(s, "16 = 16", { x: 8.1, y: 2.35, w: 4.4, h: 0.95, fontSize: 48, bold: true, color: C.accent1, fontFace: "Arial" });
  tx(s, bullets([
    "RAG 추가 답이 옮긴 원문 문장에서 조건 단어가 빠진 답 16개",
    "손으로 분류한 ‘문장 축약’ 16문항과 정확히 같다 (모두 이전 치료 문항, 채점 ‘부분’)",
    "채점자가 ‘맞음’ 준 답 중 누락으로 잡힌 것 0건",
  ], { paraSpaceAfter: 5 }), { x: 8.1, y: 3.35, w: 4.4, h: 2.1, fontSize: 13 });
  callout(s, "글자 비교는 채점자를 대신하지 못한다: 표현만 바꾼 문장도 ‘원문과 다름’으로 잡는다. 채점자가 ‘원문에 없는 덧붙임’을 표시한 답은 기본 AI 57, RAG 추가 0이다. 원문 문체가 채점에 유리했을 가능성은 임상의 κ로 확인한다.", 0.6, 5.75, 12.13, 1.0, true);
  addNote(s);
}

// ================= 18d. risk =================
{
  const s = content("오답 위험도 · C·D형 · API 없음", "틀리는 방향이 다르다: 기본 AI는 막고, RAG 추가는 허용한다", "추가 분석 · 11.15");
  table(s, [
    ["위험도", "어떤 오답"],
    ["높음 · 안전", "안전 조건(검사 수치 하한, 고령·심혈관·악성 종양 위험, 금기)에 걸리는 환자에게 약을 허용"],
    ["중간 · 삭감", "급여 기준 밖 환자에게 허용, 해외·가이드북 밖 약, 이미 실패한 약 재사용"],
    ["중간 · 지연", "급여 대상 환자를 ‘아니오’로 막음, D형에서 정답 약을 빠뜨림"],
    ["낮음 · 보류", "‘판단 불가’로 미룸, 정보가 없는데 ‘아니오’"],
  ], { x: 0.6, y: 1.7, w: 12.13, colW: [2.0, 10.13], fontSize: 13, rowH: 0.4 });
  tx(s, "C형 · 198문항 중 오답", { x: 0.6, y: 3.9, w: 5.94, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
  table(s, [["", "오답", "안전", "삭감", "지연", "보류"], ["기본 AI", "37", "1", "5", "23", "8"], ["RAG 추가", "13", "5", "1", "3", "4"]],
    { x: 0.6, y: 4.3, w: 5.94, colW: [1.44, 0.9, 0.9, 0.9, 0.9, 0.9], fontSize: 14, rowH: 0.45 });
  tx(s, "D형 · 37문항 중 틀린 문항 (문항마다 가장 높은 위험도)", { x: 6.79, y: 3.9, w: 5.94, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
  table(s, [["", "틀림", "안전", "삭감", "지연"], ["기본 AI", "25", "3", "10", "12"], ["RAG 추가", "21", "6", "5", "10"]],
    { x: 6.79, y: 4.3, w: 5.94, colW: [1.54, 1.1, 1.1, 1.1, 1.1], fontSize: 14, rowH: 0.45 });
  tx(s, "분류는 코드가 문항에 미리 적힌 ‘결정 기준’(C형)과 약별 ‘제외 이유’(D형)로 정한다. 기준은 연구자 초안이며 결과를 본 뒤 정한 사후 분석이다. 임상의 검수 때 기준을 확인받는다.", { x: 0.6, y: 5.85, w: 12.13, h: 0.75, fontSize: 12, color: C.accent3 });
  addNote(s);
}

// ================= 18d2. walkthrough C =================
{
  const s = content("한 문항 따라가기 ② · C형 · 코드 채점", "ANC 900 환자에게 Filgotinib: 체크리스트 쪽이 없으면 허용해 버린다", "추가 분석 · 11.15");
  walk(s,
    ["사례 · C-FIL-UC-anc-low (정답 ‘아니오’: ANC 1,000 이상 필요)", "45세 남성 궤양성 대장염, Mayo 6 · 내시경 2, 스테로이드·아자티오프린 무반응, 생물학제제 사용 없음. Hb 12, ANC 900, ALC 1,500. 급여 대상인가?"],
    ["기본 AI · 자료 없음", "판정: 아니오\n이유: 투여 전 ANC가 1,000 미만(900)이라 투여 시작 기준을 충족하지 못한다",
      [B("코드 채점: 맞음. "), P("허가사항의 검사 하한은 원래 알고 있었다")], "E3ECF3", C.accent1],
    ["RAG 추가 · 가져온 쪽 p.48 · 26 · 27 · 27 · 56", "판정: 예\n이유: 스테로이드·아자티오프린 무반응, Mayo 6 · 내시경 2 충족, 65세 미만 …",
      [B("코드 채점: 틀림 → 위험도 ‘높음 · 안전’. "), P("ANC 하한이 적힌 체크리스트 p.49가 5쪽 안에 없었다")], "F6E8D8", C.accent4],
    [B("코드는 ‘판정:’ 줄만 정답과 비교하고, "), P("문항에 미리 적힌 결정 기준(검사 하한)으로 위험도를 정한다. 규칙 A(고시 p.48에 체크리스트 p.49 붙이기)면 근거가 들어온다.")]);
  addNote(s);
}

// ================= 18e. safety =================
{
  const s = content("오답 위험도 · 안전 오답", "RAG 추가의 안전 오답 11건은 원인이 하나이고, 고칠 수 있다", "추가 분석 · 11.15");
  const stats = [
    ["5 대 1", "C형 안전 오답 문항 (RAG 추가 대 기본 AI)", "F6E8D8", C.accent4],
    ["6 대 3", "D형 안전 오답 문항 (RAG 추가 대 기본 AI)", "F6E8D8", C.accent4],
    ["11 / 11", "규칙 A(딸린 체크리스트 쪽 붙이기)로 RAG 추가 안전 오답의 근거 쪽이 들어온다", "E3ECF3", C.accent1],
  ];
  const w = 3.877;
  stats.forEach(([num, body, fill, col], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.7, w, 1.95, fill);
    tx(s, num, { x: x + 0.28, y: 1.85, w: w - 0.56, h: 0.8, fontSize: 40, bold: true, color: col, fontFace: "Arial" });
    tx(s, body, { x: x + 0.28, y: 2.7, w: w - 0.56, h: 0.85, fontSize: 13 });
  });
  card(s, 0.6, 3.85, 7.0, 1.95);
  label(s, "RAG 추가 11건 · 검사 수치 미달인데 허용", 0.88, 4.0, 6.5);
  tx(s, bullets([
    "Filgotinib ANC·ALC 미달(C 2), Upadacitinib Hb·ANC·ALC 미달(C 3 · D 6)",
    "체크리스트 쪽(p.49, p.52)을 못 가져온 채 “발췌에는 이 수치 기준이 없다” → 허용",
    "‘발췌에 없는 조건은 만들지 말라’는 지시가 안전 확인을 건너뛰게 함",
  ], { paraSpaceAfter: 4 }), { x: 0.88, y: 4.4, w: 6.5, h: 1.35, fontSize: 13 });
  card(s, 7.85, 3.85, 4.88, 1.95);
  label(s, "기본 AI 4건 · 68세에게 JAK 억제제 허용", 8.13, 4.0, 4.4, C.accent4);
  tx(s, "65세 이상 조항을 모름(C 1 · D 3문항, 약 5건). 가이드북을 검색하는 RAG 추가에서는 0건", { x: 8.13, y: 4.4, w: 4.4, h: 1.35, fontSize: 13 });
  callout(s, [B("제안: "), P("체크리스트 쪽 자동 첨부, 또는 근거를 못 찾으면 ‘판단 불가’로 답하게 하기. 실제로 맞히는지는 답을 다시 받아야 안다(API). 실제 진료에서는 의사가 검사 수치를 확인하므로 ‘AI 답을 그대로 따를 때의 위험’으로 해석한다.")], 0.6, 5.95, 12.13, 0.85, true);
  addNote(s);
}

// ================= 18f. other model (11.16) =================
pres.addSection({ title: "추가 실험 · 11.16 · 다른 모델" });
{
  const s = content("다른 모델로 확인 · 방법", "상위 모델(Claude Opus 5.5)에 같은 문제를 같은 조건으로 냈다", "추가 실험 · 11.16 · 다른 모델");
  const cs = [
    ["01 · 왜", "심사에서 나올 질문: ‘모델이 약해서 가이드북이 필요했던 것 아닌가?’ 다른 회사의 최상위 모델로도 같은 결론인지 본다.", null],
    ["02 · 같게 맞춘 것", bullets(["문항 380개, 지시문 그대로 (기존 코드에서 가져옴)", "RAG 추가: gpt가 검색한 5쪽을 그대로 넣음 → 검색 결과 동일", "추론 강도 medium (두 모델 기본값)", "채점: A·A2 gpt-6-sol v2.1, C·D 코드"]), "E3ECF3"],
    ["03 · 다른 것", "답하는 모델만 바꿨다: gpt-5.6-terra → Claude Opus 5.5 (Anthropic 최상위급). 답은 1회, A·A2형 채점도 1회.", null],
  ];
  const w = 3.877;
  cs.forEach(([lab, body, fill], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 2.55, fill);
    label(s, lab, x + 0.28, 1.95, w - 0.56);
    tx(s, body, { x: x + 0.28, y: 2.38, w: w - 0.56, h: 1.85, fontSize: 14, paraSpaceAfter: 3 });
  });
  table(s, [
    ["단계", "방식", "요청", "걸린 시간", "비용 (실측)"],
    ["Claude 답 (네 유형 × 두 대상)", "Anthropic 배치 API", "760 (파일럿 20 + 740)", "약 4분", "$6.66"],
    ["A·A2형 채점", "OpenAI 배치 API · gpt-6-sol", "290", "약 4분", "$1.94"],
    ["C·D형 채점", "코드", "470", "–", "없음"],
  ], { x: 0.6, y: 4.5, w: 12.13, colW: [3.4, 3.2, 2.33, 1.5, 1.7], fontSize: 14, rowH: 0.42 });
  tx(s, "배치 API: 요금 절반. 보낸 요청은 일반 호출과 글자까지 같음을 확인했다. 실패 0건. 배치는 ‘24시간 안 처리’만 보장해 이번처럼 빠르지 않을 수 있다.", { x: 0.6, y: 6.3, w: 12.13, h: 0.55, fontSize: 12, color: C.accent3 });
  addNote(s);
}

{
  const s = content("다른 모델 · 정확도", "상위 모델도 가이드북 없이는 낮고, 붙이면 더 정확했다", "추가 실험 · 11.16 · 다른 모델");
  table(s, [
    ["유형", "gpt 기본", "gpt + RAG", "Opus 기본", "Opus + RAG"],
    ["A 본 점수 · 101", "0.441", "0.807", "0.470", "0.911"],
    ["A2 · 38", "0.092", "0.908", "0.184", "0.934"],
    ["C 정답률 · 198", "0.813", "0.934", "0.823", "0.975"],
    ["D 완전 일치 · 37", "0.324", "0.432", "0.378", "0.622"],
  ], { x: 0.6, y: 1.75, w: 7.0, colW: [1.85, 1.15, 1.35, 1.15, 1.5], fontSize: 14, rowH: 0.44 });
  tx(s, "A형 기준별 (기본 → RAG 추가)", { x: 0.6, y: 4.35, w: 7.0, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
  table(s, [
    ["기준", "gpt-5.6-terra", "Opus 5.5"],
    ["유지 기준 · 25", "0.12 → 0.90", "0.06 → 0.80"],
    ["이전 치료 · 25", "0.30 → 0.68", "0.44 → 0.96"],
    ["나이 · 7 / 고령 · 7", "0.29 / 0.14 → 1.00", "0.14 / 0.43 → 1.00"],
  ], { x: 0.6, y: 4.72, w: 7.0, colW: [2.6, 2.2, 2.2], fontSize: 13, rowH: 0.36 });
  card(s, 7.85, 1.75, 4.88, 4.9, "E3ECF3");
  label(s, "Claude Opus 5.5 · A형 본 점수", 8.13, 1.95, 4.4);
  tx(s, "0.47 → 0.91", { x: 8.13, y: 2.35, w: 4.4, h: 0.8, fontSize: 38, bold: true, color: C.accent1, fontFace: "Arial" });
  tx(s, bullets([
    "가이드북 없이는 gpt(0.44)와 비슷: 국내 고유 기준은 상위 모델도 모른다",
    "RAG 추가가 나은 문항 60 / 못한 문항 5 (부호검정 p = 5×10⁻¹³)",
    "이전 치료 0.96: gpt + RAG의 ‘조건 축약’이 거의 없었다",
    "D형: 같은 5쪽에서 재현율 0.90 · 정밀도 0.96, 실패한 약 재사용 0",
  ], { paraSpaceAfter: 6 }), { x: 8.13, y: 3.25, w: 4.4, h: 3.3, fontSize: 13 });
  tx(s, "A·A2형은 두 모델 모두 gpt-6-sol 첫 회 채점(gpt 3회 다수결도 0.436 → 0.807로 거의 같음). 채점자가 OpenAI라도 Opus 답이 더 높게 나왔다.", { x: 0.6, y: 6.42, w: 7.0, h: 0.5, fontSize: 11, color: C.accent3 });
  addNote(s);
}

{
  const s = content("다른 모델 · 안전 오답", "같은 발췌에서 안전 오답은 다른 두 모델에도 남았다", "추가 실험 · 11.16 · 다른 모델");
  tx(s, "gpt + RAG가 안전 오답을 낸 11문항 · 세 모델 모두 체크리스트 쪽이 빠진 같은 5쪽을 받음", { x: 0.6, y: 1.7, w: 12.13, h: 0.35, fontSize: 15, bold: true, color: C.text1 });
  table(s, [
    ["문항", "gpt-5.6-terra + RAG", "Claude Opus 5.5 + RAG", "Qwen3-14B + RAG"],
    ["C형 5 · 검사 수치 미달 환자 (정답 ‘아니오’)", "5개 모두 ‘예’ (허용)", "‘판단 불가’ 4 · ‘예’ 1", "5개 모두 ‘예’ (허용)"],
    ["D형 6 · Hb 7.5 · ANC 900 · ALC 450", "6개 모두 Upadacitinib 포함", "6개 모두 Upadacitinib 포함", "6개 모두 Upadacitinib 포함"],
  ], { x: 0.6, y: 2.1, w: 12.13, colW: [3.73, 2.8, 2.8, 2.8], fontSize: 13, rowH: 0.48 });
  tx(s, "‘높음 · 안전’ 오답 문항 수 (risk_analysis.py와 같은 규칙)", { x: 0.6, y: 3.75, w: 6.0, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
  table(s, [["", "C형", "D형"], ["gpt 기본 AI", "1", "3"], ["gpt + RAG", "5", "6"], ["Opus 기본 AI", "4", "3"], ["Opus + RAG", "1", "6"], ["Qwen 기본 AI", "8", "2"], ["Qwen + RAG", "6", "6"]],
    { x: 0.6, y: 4.12, w: 6.0, colW: [2.6, 1.7, 1.7], fontSize: 13, rowH: 0.36 });
  card(s, 6.9, 3.75, 5.83, 1.5, "E3ECF3");
  tx(s, [B("하나만 판정할 때 (C형): "), P("Opus는 “발췌에는 투여 전 기준치가 없다”며 판단을 미뤘다 → 위험도 ‘낮음 · 보류’로 내려감")], { x: 7.18, y: 3.85, w: 5.3, h: 1.4, fontSize: 14, valign: "middle" });
  card(s, 6.9, 5.4, 5.83, 1.45, "F6E8D8");
  tx(s, [B("여러 약을 고를 때 (D형): "), P("세 모델 모두 위험한 약을 넣었다 → 모델보다 검색 구조(체크리스트 쪽 누락)의 문제. Qwen은 C형에서도 gpt처럼 5개 모두 허용")], { x: 7.18, y: 5.42, w: 5.3, h: 1.41, fontSize: 13, valign: "middle" });
  addNote(s);
}

{
  const s = content("다른 모델 · Opus 기준 발견", "Opus로 다시 보면: 결론은 같고, 틀리는 방식은 달랐다", "추가 실험 · 11.16 · 다른 모델");
  table(s, [
    ["발견 (같은 규칙으로 계산)", "gpt-5.6-terra", "Claude Opus 5.5"],
    ["기본 AI · A 이전 치료 오답 중 TNF 언급", "10 / 10", "0 / 3"],
    ["기본 AI · C 급여 대상 막음 (TNF·생물학제제 이유)", "23 (11)", "14 (0)"],
    ["기본 AI · 해외 약 Risankizumab 쓴 사례", "3", "3"],
    ["기본 AI · 원문에 없는 덧붙임 답 (A / A2)", "39 / 18", "40 / 11"],
    ["기본 AI · 68세에게 JAK 허용 (안전, C / D)", "1 / 3", "4 / 3"],
    ["RAG 추가 · A 맞음 / 부분 / 틀림", "73 / 17 / 11", "92 / 0 / 9"],
    ["RAG 추가 · A 조건 축약 (코드로 셈)", "16", "0"],
    ["RAG 추가 · D 빠뜨린 약 (모두 고시 쪽 미검색)", "43", "21"],
    ["RAG 추가 · D 쪽 없이 기억으로 맞게 넣은 약", "27", "49"],
    ["RAG 추가 · D 이미 실패한 약 재사용", "4", "0"],
    ["RAG 추가 · C 오답 (허용 / 막음 / 판단 불가)", "6 / 3 / 1", "1 / 0 / 4"],
    ["RAG 추가 · 안전 오답 (C / D)", "5 / 6", "1 / 6"],
  ], { x: 0.6, y: 1.65, w: 8.2, colW: [4.4, 1.9, 1.9], fontSize: 12, rowH: 0.36 });
  card(s, 9.05, 1.65, 3.68, 5.15, "E3ECF3");
  label(s, "Opus 기준으로 정리하면", 9.3, 1.85, 3.2);
  tx(s, bullets([
    "기본 AI: 외국·예전 기준(TNF 실패 요구)은 섞지 않았다. 대신 유지 ‘또는’을 ‘그리고’로, 소아·베체트 기준을 잘못 기억해 막았다",
    "지어낸 덧붙임·해외 약은 gpt와 비슷 → 기억만으로는 상위 모델도 부정확",
    "RAG 추가: 축약·막는 오답이 사라짐. 남은 A형 9개 중 7개는 쪽을 못 찾은 경우",
    "D형은 빠진 쪽을 기억으로 메움(Vedolizumab 20). 새 경구약(Ozanimod 11 등)은 못 메움",
    "D형 안전 오답 6건은 같다 → 검색 구조 문제",
  ], { paraSpaceAfter: 5 }), { x: 9.3, y: 2.25, w: 3.25, h: 4.45, fontSize: 12 });
  addNote(s);
}

{
  const s = content("다른 모델 · 공개 모델", "공개 모델(Qwen3-14B)도 가이드북을 붙이면 크게 올랐다", "추가 실험 · 11.16 · 다른 모델");
  table(s, [
    ["유형 (기본 → RAG 추가)", "gpt-5.6-terra", "Claude Opus 5.5", "Qwen3-14B"],
    ["A 본 점수 · 101", "0.44 → 0.81", "0.47 → 0.91", "0.08 → 0.63"],
    ["A2 · 38", "0.09 → 0.91", "0.18 → 0.93", "0.03 → 0.58"],
    ["C 정답률 · 198", "0.81 → 0.93", "0.82 → 0.98", "0.65 → 0.91"],
    ["D 완전 일치 · 37 *", "0.32 → 0.43", "0.38 → 0.62", "0.03 → 0.27"],
    ["RAG 추가가 나음 / 못함 (A)", "51 / 5", "60 / 5", "68 / 4"],
  ], { x: 0.6, y: 1.75, w: 7.6, colW: [2.5, 1.7, 1.7, 1.7], fontSize: 13, rowH: 0.42 });
  table(s, [
    ["단계", "방식", "비용 (실측)"],
    ["답 760개", "GPU 서버 · vLLM · 원본 bf16 · 생각 모드 켬", "없음 (약 15분)"],
    ["A·A2형 채점 290", "OpenAI 배치 · gpt-6-sol", "$1.91"],
  ], { x: 0.6, y: 4.5, w: 7.6, colW: [1.9, 4.2, 1.5], fontSize: 12, rowH: 0.36 });
  tx(s, "같은 문항·지시문·샘플링, RAG 추가는 gpt가 검색한 같은 5쪽. * D형은 약 이름 표기(예: ‘아다리무맙’)를 정답으로 볼지 정하기 전 잠정값.", { x: 0.6, y: 5.75, w: 7.6, h: 0.75, fontSize: 11, color: C.accent3 });
  card(s, 8.45, 1.75, 4.28, 4.9, "E3ECF3");
  label(s, "Qwen3-14B · A형 본 점수", 8.73, 1.95, 3.8);
  tx(s, "0.08 → 0.63", { x: 8.73, y: 2.35, w: 3.8, h: 0.8, fontSize: 36, bold: true, color: C.accent1, fontFace: "Arial" });
  tx(s, bullets([
    "가이드북 없이는 거의 모른다: A 101문항 중 91개를 ‘적혀 있지 않다’로 답함",
    "붙였을 때 오른 폭은 가장 크다 (나음 68 / 못함 4)",
    "C형 RAG 추가 0.91: gpt(0.93)와 비슷",
    "A·A2형은 발췌가 있어도 큰 모델보다 0.27~0.36 낮다",
  ], { paraSpaceAfter: 6 }), { x: 8.73, y: 3.25, w: 3.8, h: 3.3, fontSize: 13 });
  addNote(s);
}

{
  const s = content("다른 모델 · Qwen 기준 발견", "Qwen으로 보면: 모르면 ‘없다’고 하고, 붙이면 비슷한 기준을 헷갈렸다", "추가 실험 · 11.16 · 다른 모델");
  table(s, [
    ["발견 (같은 규칙으로 계산)", "gpt", "Opus", "Qwen"],
    ["기본 AI · A ‘적혀 있지 않다’ 답 (101 중)", "6", "8", "91"],
    ["기본 AI · A 이전 치료 오답 중 TNF 언급", "10 / 10", "0 / 3", "2 / 24"],
    ["기본 AI · 원문에 없는 덧붙임 답 (A / A2)", "39 / 18", "40 / 11", "8 / 4"],
    ["기본 AI · 해외 약 / 알아보지 못한 약 이름 (D)", "3 / 0", "3 / 0", "0 / 21"],
    ["RAG 추가 · A 맞음 / 부분 / 틀림", "73 / 17 / 11", "92 / 0 / 9", "55 / 18 / 28"],
    ["RAG 추가 · A 활성도 기준 점수 (25문항)", "0.80", "1.00", "0.44"],
    ["RAG 추가 · A 조건 축약 (코드로 셈)", "16", "0", "15"],
    ["RAG 추가 · D 빠뜨린 약 (그중 고시 쪽 미검색)", "43 (43)", "21 (21)", "57 (46)"],
    ["RAG 추가 · D 쪽 없이 기억으로 맞게 넣은 약", "27", "49", "24"],
    ["RAG 추가 · C 오답 (허용 / 막음 / 판단 불가)", "6 / 3 / 1", "1 / 0 / 4", "12 / 1 / 4"],
    ["RAG 추가 · 안전 오답 (C / D)", "5 / 6", "1 / 6", "6 / 6"],
  ], { x: 0.6, y: 1.65, w: 8.2, colW: [4.3, 1.3, 1.3, 1.3], fontSize: 12, rowH: 0.38 });
  card(s, 9.05, 1.65, 3.68, 5.15, "E3ECF3");
  label(s, "Qwen 기준으로 정리하면", 9.3, 1.85, 3.2);
  tx(s, bullets([
    "기본 AI: 지어내기보다 ‘가이드북에 없다’고 답했다 → 점수는 낮지만 덧붙임·TNF 혼동은 적다",
    "약 이름을 한글로 옮기다 틀렸다(D 21문항, 다른 나라 글자 섞임 포함)",
    "RAG 추가: 같은 쪽의 비슷한 숫자를 헷갈렸다. 활성도를 물었는데 ‘지속 투여’ 기준을 답함",
    "틀릴 때 허용 쪽이 많다(C 12), 축약은 gpt와 비슷(15)",
    "D형 안전 오답 6건은 세 모델이 같다 → 검색 구조 문제",
  ], { paraSpaceAfter: 5 }), { x: 9.3, y: 2.25, w: 3.25, h: 4.45, fontSize: 12 });
  addNote(s);
}

{
  const s = content("오류 분석 · 세 모델", "좋은 모델일수록 남은 오답은 검색 문제였다", "추가 실험 · 11.16 · 다른 모델");
  tx(s, "A형 RAG 추가가 잃은 점수 (101점 중, 원인별)", { x: 0.6, y: 1.65, w: 7.6, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
  table(s, [
    ["원인 (코드 분류)", "gpt", "Opus", "Qwen"],
    ["검색 · 근거 쪽을 못 가져옴", "6.0", "7.0", "6.5"],
    ["읽기 · 같은 쪽의 다른 기준을 옮김", "5.0", "0", "13.0"],
    ["답변 · 조건 축약 (금기·내약성 생략)", "7.5", "0", "9.5"],
    ["그 밖의 답변·읽기 (덧붙임, ‘적혀 있지 않다’ 등)", "1.0", "2.0", "8.0"],
    ["합계", "19.5", "9.0", "37.0"],
  ], { x: 0.6, y: 2.02, w: 7.6, colW: [4.6, 1.0, 1.0, 1.0], fontSize: 13, rowH: 0.38 });
  tx(s, "C형 오답 방향 · D형 빠뜨린 약", { x: 0.6, y: 4.45, w: 7.6, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
  table(s, [
    ["", "gpt", "Opus", "Qwen"],
    ["C형 오답 (허용 / 미룸 / 막음·단정)", "13 (6 / 1 / 6)", "5 (1 / 4 / 0)", "17 (12 / 4 / 1)"],
    ["D형 빠뜨린 약 (검색 / 읽기)", "43 / 0", "21 / 0", "46 / 8"],
  ], { x: 0.6, y: 4.82, w: 7.6, colW: [3.4, 1.4, 1.4, 1.4], fontSize: 12, rowH: 0.38 });
  tx(s, "세 모델은 같은 5쪽을 받았다. 분류는 코드 규칙(error_analysis_models.py)이며 gpt 손 분류 28건 중 27건과 같다.", { x: 0.6, y: 6.12, w: 7.6, h: 0.5, fontSize: 11, color: C.accent3 });
  card(s, 8.45, 1.65, 4.28, 5.15, "E3ECF3");
  label(s, "세 모델이 모두 틀린 문항", 8.73, 1.85, 3.8);
  tx(s, bullets([
    "A 7 · A2 4 · C 5 · D 14, 원인은 모두 ‘근거 쪽 없음’",
    "체크리스트 p.49·52: 검사 하한 A 3, C 5, D 안전 오답 6",
    "IV 고시 p.36·37 대신 SC 쪽: Infliximab IV UC·베체트 4",
    "투약간격 p.28 대신 다른 약 쪽: Adalimumab 처방 기간 4",
    "Opus: 잃은 9점 중 7점이 검색 → 모델을 바꿔도 남는 오답",
    "Qwen: 쪽이 있어도 시작 기준 대신 지속 기준을 옮김(13)",
  ], { paraSpaceAfter: 5 }), { x: 8.73, y: 2.25, w: 3.8, h: 4.45, fontSize: 12 });
  addNote(s);
}

{
  const s = content("오류 분석 · 개선 방향", "정확도를 올리려면: 검색부터, 그다음 답 지시문", "추가 실험 · 11.16 · 다른 모델");
  table(s, [
    ["#", "방법", "겨냥하는 오답", "효과가 클 모델"],
    ["1", "체크리스트·투약간격 쪽 자동 첨부 (규칙 A)", "세 모델 공통 A 3 · C 5 · D 안전 6, A2 4", "모두 · 안전 오답"],
    ["2", "질문의 약·제형으로 고시 쪽 붙이기, D형은 약별 검색 (규칙 B)", "IV/SC 혼동 4, D 빠뜨린 약 21~46", "모두 (Opus는 남은 오답 대부분)"],
    ["3", "답 지시문: 조건 문장 전체 인용, 시작·지속 기준 구분", "축약 15~17, 다른 기준 5~13", "gpt · Qwen"],
    ["4", "D형 규칙 기반: AI는 환자 사실만, 판정은 코드", "D형 전체, 실패 약 재사용, 계산 오류", "모두"],
    ["5", "약 이름은 영문 성분명으로", "Qwen 이름 표기 오류 32", "Qwen"],
    ["6", "근거를 못 찾으면 ‘판단 불가’", "허용 쪽 안전 오답", "gpt · Qwen"],
  ], { x: 0.6, y: 1.65, w: 12.13, colW: [0.5, 5.0, 4.13, 2.5], fontSize: 13, rowH: 0.48 });
  callout(s, [B("기대 효과: "), P("1·2번만으로 A형 최대 +0.06~0.07 (세 모델 모두). 실제로 맞히는지는 답을 다시 받아야 안다(API). 이 오답을 보고 만든 개선이라 사후 분석으로 보고한다.")], 0.6, 5.2, 5.94, 1.5);
  callout(s, [B("약 이름 표기: "), P("철자 변형을 정답으로 쳐도 Qwen D형은 0.27 → 0.30(기본 AI 그대로). 채점은 엄격하게 두고 참고값을 함께 보고하자. 이름 4개는 해외 약(Certolizumab 3, Secukinumab 1)")], 6.79, 5.2, 5.94, 1.5, true);
  addNote(s);
}

// ================= 18b. code =================
pres.addSection({ title: "코드와 재현" });
{
  const s = content("코드와 재현", "모든 결과는 코드로 다시 만들 수 있게 남겼다", "코드와 재현");
  table(s, [
    ["단계", "스크립트 (STAGE1/)", "API", "결과"],
    ["문항 만들기", "make_a · make_a2 · make_c · make_d", "없음", "output/*_items.jsonl"],
    ["답 받기", "eval_a (기본 AI · RAG 추가)", "gpt-5.6-terra", "eval_out/<실행>/answers.jsonl"],
    ["채점", "regrade_v2 (A·A2) · score_cases (C·D)", "gpt-6-sol / 없음", "graded_v21 · graded_code"],
    ["검수표", "make_review_xlsx · make_csv_review · make_judge_check", "없음", "output/검수표_*.xlsx"],
    ["분석 1", "analyze_errors · simulate_retrieval · sensitivity_additions", "없음", "오답원인분류 · 시뮬레이션 · 민감도"],
    ["분석 2", "quote_check · risk_analysis", "없음", "인용문원문대조 · 오답위험도"],
    ["다른 모델 · 11.16", "eval_claude_batch · regrade_v2_batch · compare_models", "Opus 5.5 · gpt-6-sol (배치)", "*_claude-opus-5-5 · 모델비교.md"],
    ["공개 모델 · 11.16", "eval_local_mlx (맥) · eval_local_cuda (GPU 서버)", "없음 (직접 실행)", "*_qwen3-14b-bf16 · 모델별발견"],
  ], { x: 0.6, y: 1.75, w: 12.13, colW: [1.7, 4.73, 2.3, 3.4], fontSize: 12, rowH: 0.33 });
  card(s, 0.6, 4.85, 5.94, 1.6);
  label(s, "지우지 않고 보존", 0.88, 5.0, 5.4);
  tx(s, bullets(["고치기 전 답·채점은 superseded_*.jsonl로 옮겨 둠", "일회용 스크립트·옛 사본은 _archive/로 옮김 (삭제 0)", "옛 채점 코드(v1)와 보기형 D형 코드도 그대로 둠"], { paraSpaceAfter: 3 }), { x: 0.88, y: 5.36, w: 5.4, h: 1.05, fontSize: 13 });
  card(s, 6.79, 4.85, 5.94, 1.6, "E3ECF3");
  label(s, "재현 확인 · 11.15", 7.07, 5.0, 5.4);
  tx(s, bullets(["11.10 채점 비교를 보존 파일로 다시 계산", "v2.1 비교: 저장된 결과와 글자까지 같음", "v2 비교: 숫자 모두 같음 (표기만 다름)"], { paraSpaceAfter: 3 }), { x: 7.07, y: 5.36, w: 5.4, h: 1.05, fontSize: 13 });
  addNote(s);
}

// ================= 19. limits =================
pres.addSection({ title: "한계와 다음 단계" });
{
  const s = content("한계", "논문에 밝혀야 할 것", "한계와 다음 단계");
  const items = [
    ["임상의 검증 없음", "문항·채점·오류 분류·위험도 기준 모두 아직 사람 검증 전 (오류 분류와 편향 점검은 Claude)"],
    ["1회 측정", "답 1회. SC 22문항 재질문에서 기본 AI 판정 9개가 바뀜. 채점 3회는 A형 74문항에만"],
    ["답하는 모델 셋, 채점자 하나", "gpt-5.6-terra · Claude Opus 5.5 · Qwen3-14B(11.16, 둘 다 gpt가 검색한 쪽 재사용). 채점자는 OpenAI(gpt-6-sol) 하나"],
    ["결과를 본 뒤 정한 규칙", "채점 규칙 일부, 검색 개선 규칙, 인용문 대조·위험도 기준은 결과를 보고 정함 → 사후 분석으로 보고"],
    ["문항이 독립이 아님", "A형 101문항이 내용 묶음 30개 → 묶음 단위 신뢰구간 함께 보고"],
    ["범위", "2024 가이드북 한 판, 가이드북만 검색하는 모드. D형 정답은 코드 규칙으로 계산"],
  ];
  items.forEach(([t, b], i) => {
    const x = 0.6 + (i % 2) * 6.19, y = 1.75 + Math.floor(i / 2) * 1.6;
    card(s, x, y, 5.94, 1.45);
    tx(s, t, { x: x + 0.3, y: y + 0.2, w: 5.3, h: 0.4, fontSize: 17, bold: true, color: C.text1 });
    tx(s, b, { x: x + 0.3, y: y + 0.62, w: 5.3, h: 0.75, fontSize: 14 });
  });
  addNote(s);
}

// ================= 20. next =================
{
  const s = content("다음 단계", "검증을 먼저, 개선은 사후 분석으로", "한계와 다음 단계");
  table(s, [
    ["#", "단계", "내용", "API 비용 (추정)"],
    ["1", "임상의 2인 검수", "문항 표본 114 + 결정 20 (+ 위험도 기준). 배포용 검수표·요청문 초안 준비됨", "없음"],
    ["2", "정답 쪽 직접 제공", "검색을 건너뛰고 근거 쪽을 넣어 검색 상한을 잰다", "배치 약 $4~6"],
    ["3", "규칙 B 적용", "딸린 쪽·약별 쪽을 붙여 답을 다시 받는다 (사후 분석)", "실행 전 보고"],
    ["4", "반복 측정", "답 3회·채점 3회 → 채점자 검증표 → 임상의 κ", "배치 약 $10~20"],
    ["5", "D형 규칙 기반 비교", "LLM은 환자 사실만 뽑고 규칙이 판정. 새 사례로 검증", "약 $1 미만"],
  ], { x: 0.6, y: 1.75, w: 12.13, colW: [0.6, 2.7, 6.33, 2.5], fontSize: 15, rowH: 0.6 });
  tx(s, "API는 연구자가 승인할 때만 쓰고, 실행 전에 호출 수·모델·비용을 보고한다. 앞으로는 배치 API(요금 절반)로 돌린다. 누적: 11.15까지 약 $34~45(추정) + 11.16 상위 모델 실험 $8.6 + 공개 모델 채점 $1.9(실측).", { x: 0.6, y: 5.75, w: 12.1, h: 0.7, fontSize: 13, color: C.accent3 });
  addNote(s);
}

// ================= 21. develop =================
{
  const s = content("발전 방향", "논문을 키울 수 있는 추가 분석", "한계와 다음 단계");
  const cols = [
    ["완료 · 11.15–16", null, [
      ["오답의 방향과 위험도 · 완료", "안전 오답은 RAG 추가가 더 많음(C형 5 대 1, D형 6 대 3). 원인은 체크리스트 쪽 미검색 하나. 기준은 임상의 확인 필요"],
      ["인용문 원문 대조 · 완료", "원문 일치도 RAG 추가 0.70, 기본 AI 0.30. 축약 16건을 코드로 재현(맞은 답 오탐 0)"],
      ["다른 모델 비교 · 11.16 완료", "Opus 5.5(A형 0.47 → 0.91)와 공개 모델 Qwen3-14B(0.08 → 0.63)로 같은 결론. D형 안전 오답 6건은 세 모델 모두 같음 → 검색 구조 문제"],
    ]],
    ["적은 비용 · 승인 후", "F6E8D8", [
      ["안전 오답 재확인", "규칙 A로 체크리스트 쪽을 붙여 안전 오답 11문항만 두 모델에 다시 묻기. 실제로 허용을 멈추는지 확인"],
      ["축약 방지 프롬프트", "A형 최대 감점 원인은 검색이 아니라 축약. ‘조건을 빠짐없이’ 또는 ‘원문 인용 후 답’으로 A형만 다시 받기"],
      ["더 큰 공개 모델", "GPU 서버에서 27B급 공개 모델로 같은 실험. 답 받기는 요금 없음, A·A2형 채점만 배치 약 $2"],
    ]],
  ];
  cols.forEach(([t, fill, rows], i) => {
    const x = 0.6 + i * 6.19;
    card(s, x, 1.75, 5.94, 4.8, fill);
    label(s, t, x + 0.3, 1.95, 5.3, i ? C.accent4 : C.accent1);
    rows.forEach(([h, b], j) => {
      const y = 2.4 + j * 1.38;
      tx(s, h, { x: x + 0.3, y, w: 5.34, h: 0.36, fontSize: 15, bold: true, color: C.text1 });
      tx(s, b, { x: x + 0.3, y: y + 0.38, w: 5.34, h: 0.95, fontSize: 13 });
    });
  });
  addNote(s);
}

// ================= 22. discussion =================
{
  const s = content("논의", "오늘 정하고 싶은 것", "한계와 다음 단계");
  const ds = [
    ["01 · 임상의 검수", "검수자 2인 섭외와 일정. 검수표(문항 380행 + 결정 20행)와 요청문 초안은 준비됨", null],
    ["02 · 위험도 · 채점 기준", "오답 위험도 4단계 기준 확인. 예: 65세 이상 JAK 조항을 ‘안전’으로 볼지 ‘삭감’으로 볼지. D형에서 철자만 다른 약 이름을 정답으로 볼지", null],
    ["03 · 다음 실험 순서", [B("제안: "), P("안전 오답 11문항 재질문(두 모델, 수천 원) → 정답 쪽 직접 제공(배치 약 $4~6) → 반복 측정(배치 약 $10~20)")], "E3ECF3"],
    ["04 · 투고 방향", "목표 학술지를 정하면 그 보고 지침(예: TRIPOD-LLM)에 맞춰 원고 체크리스트를 채운다", null],
  ];
  ds.forEach(([lab, body, fill], i) => {
    const x = 0.6 + (i % 2) * 6.19, y = 1.75 + Math.floor(i / 2) * 2.55;
    card(s, x, y, 5.94, 2.3, fill);
    label(s, lab, x + 0.3, y + 0.28, 5.3);
    tx(s, body, { x: x + 0.3, y: y + 0.72, w: 5.3, h: 1.45, fontSize: 16 });
  });
  addNote(s);
}

(async () => {
  const unused = Object.keys(NOTES).filter((k) => !USED.has(k));
  if (unused.length) throw new Error("쓰이지 않은 대본: " + unused.join(", "));
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
