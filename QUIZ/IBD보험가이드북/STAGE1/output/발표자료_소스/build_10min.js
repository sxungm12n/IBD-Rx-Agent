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
    { text: { text: "IBD 보험가이드북 RAG 기능 추가 평가 · 2026-11-16 · 10분 요약", options: { x: 0.6, y: 6.98, w: 8, h: 0.3, fontSize: 10, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: 12.13, y: 6.98, w: 0.6, h: 0.3, fontSize: 10, color: C.accent3, align: "right", margin: 0 },
});

// ---------- notes (발표 대본: notes.json, 슬라이드 제목 → 대본) ----------
const NOTES = require("./notes_10min.json");
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

// ================= 10분 요약 덱 (10장) · 2026-11-16 =================
// 숫자는 모두 eval_out/ 결과와 보고서(모델비교·모델별발견·오답원인_모델별·오류분석_세모델_정리)에서 옮겼다.
const SEC = ["질문과 결론", "결과", "오류와 안전", "다음 단계"];

// 1. 표지
pres.addSection({ title: SEC[0] });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: SEC[0] });
  s._title = "표지";
  s.addText("연구 진행 보고 · 2026-11-16 · 10분 요약", { placeholder: "eyebrow" });
  s.addText("IBD 보험가이드북\nRAG 기능 추가 평가", { placeholder: "title" });
  s.addText("같은 AI에 RAG 기능(2024 대한장연구학회 보험가이드북 검색)을 추가하면 국내 급여 기준 답이 얼마나 정확해지는가. 세 모델(gpt-5.6-terra · Claude Opus 5.5 · Qwen3-14B)로 확인했다.", { placeholder: "body" });
  tx(s, "모든 수치는 답 1회 · 채점 1회, 임상의 검증 전이다.", { x: 0.8, y: 5.9, w: 11, h: 0.4, fontSize: 13, color: C.accent6 });
  addNote(s);
}

// 2. 핵심 결론
{
  const s = content("요약", "핵심 결론 세 가지", SEC[0]);
  const ks = [
    ["01 · 정확도", "RAG를 추가하면 세 모델 모두 크게 올랐다", "0.44 → 0.81", "A형 · gpt-5.6-terra\nOpus 0.47 → 0.91 · Qwen 0.08 → 0.63", null],
    ["02 · 오류", "좋은 모델일수록 남은 오답은 검색 문제", "7 / 9점", "Opus가 잃은 점수 중 검색 몫\n세 모델이 모두 틀린 문항은 전부 ‘근거 쪽 없음’", "E3ECF3"],
    ["03 · 안전", "위험한 오답은 RAG를 추가했을 때 생겼다", "6 = 6 = 6", "검사 수치 미달 환자에게 Upadacitinib\n세 모델이 같은 6문항 → 체크리스트 쪽 누락", "F6E8D8"],
  ];
  const w = 3.877;
  ks.forEach(([lab, head, big, sub, fill], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 4.7, fill);
    label(s, lab, x + 0.3, 1.97, w - 0.6, fill === "F6E8D8" ? C.accent4 : C.accent1);
    tx(s, head, { x: x + 0.3, y: 2.4, w: w - 0.6, h: 1.0, fontSize: 19, bold: true, color: C.text1 });
    tx(s, big, { x: x + 0.3, y: 3.5, w: w - 0.6, h: 0.9, fontSize: 36, bold: true, color: fill === "F6E8D8" ? C.accent4 : C.accent1, fontFace: "Arial" });
    tx(s, sub, { x: x + 0.3, y: 4.5, w: w - 0.6, h: 1.8, fontSize: 14 });
  });
  addNote(s);
}

// 3. 방법
{
  const s = content("방법", "같은 문제를, RAG가 없을 때와 있을 때 비교했다", SEC[0]);
  table(s, [
    ["유형", "문항", "묻는 것 (예)", "채점"],
    ["A 급여 기준", "101", "Infliximab 성인 크론병 활성도 기준은? → CDAI 220 이상", "AI 채점자"],
    ["A2 추가 규칙", "38", "처방 기간·재투여·용량 증량 규칙", "AI 채점자"],
    ["C 환자 판정", "198", "이 환자가 급여 대상인가? 예 / 아니오 / 판단 불가", "코드"],
    ["D 약 고르기", "37", "이 환자에게 급여되는 약을 보기 없이 모두 쓰시오", "코드"],
  ], { x: 0.6, y: 1.75, w: 7.7, colW: [1.6, 0.8, 4.1, 1.2], fontSize: 13, rowH: 0.5 });
  tx(s, "문항 380개는 가이드북 CSV에서 코드로 만들었다(LLM 안 씀). 연구자 1차 검수 완료, 임상의 검수 전. AI 채점자는 gpt-6-sol(답한 대상은 모름).", { x: 0.6, y: 4.45, w: 7.7, h: 0.8, fontSize: 12, color: C.accent3 });
  card(s, 8.55, 1.75, 4.18, 1.55);
  label(s, "기본 AI · 책을 덮고", 8.85, 1.92, 3.6);
  tx(s, "자료 없이 기억으로 답한다", { x: 8.85, y: 2.35, w: 3.6, h: 0.8, fontSize: 15 });
  card(s, 8.55, 3.45, 4.18, 1.8, "E3ECF3");
  label(s, "기본 AI + RAG 추가 · 오픈북", 8.85, 3.62, 3.6);
  tx(s, "같은 AI가 가이드북에서 검색한 5쪽을 함께 받아 답한다. 다른 조건은 모두 같다", { x: 8.85, y: 4.05, w: 3.6, h: 1.1, fontSize: 15 });
  card(s, 0.6, 5.45, 12.13, 1.3);
  tx(s, [B("답한 모델 셋: "), P("gpt-5.6-terra(주 실험) · Claude Opus 5.5(상위 모델) · Qwen3-14B(공개 모델, GPU 서버). RAG를 추가할 때 Opus와 Qwen에는 gpt 실행 때 검색한 같은 5쪽을 넣어, 바뀐 것은 답하는 모델뿐이다.")],
    { x: 0.9, y: 5.5, w: 11.5, h: 1.2, fontSize: 15, valign: "middle" });
  addNote(s);
}

// 3b. RAG를 어떻게 추가했나
{
  const s = content("방법 · RAG 추가", "RAG 기능은 이렇게 추가했다: 가이드북 검색 → 5쪽을 질문과 함께", SEC[0]);
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

// 4. 정확도
pres.addSection({ title: SEC[1] });
{
  const s = content("결과 · 정확도", "세 모델 모두 RAG를 추가하면 정확해졌다", SEC[1]);
  // 막대 그래프 (도형으로 그림: Keynote·Google Slides 어디서나 같게 보이도록)
  tx(s, "A형 본 점수 (101문항)", { x: 0.6, y: 1.7, w: 5.6, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
  card(s, 0.75, 2.15, 0.25, 0.22, HEX.accent6); tx(s, "기본 AI", { x: 1.07, y: 2.12, w: 1.3, h: 0.3, fontSize: 12 });
  card(s, 2.35, 2.15, 0.25, 0.22, HEX.accent1); tx(s, "RAG 추가", { x: 2.67, y: 2.12, w: 1.8, h: 0.3, fontSize: 12 });
  const base = 5.95, H = 3.1;
  s.addShape(SH.LINE, { x: 0.6, y: base, w: 5.6, h: 0, line: { color: "C9CFD2", width: 1 }, objectName: "axis" });
  [["gpt-5.6-terra", 0.441, 0.807], ["Claude Opus 5.5", 0.470, 0.911], ["Qwen3-14B", 0.084, 0.634]].forEach(([m, v1, v2], i) => {
    const gx = 0.75 + i * 1.85;
    [[v1, HEX.accent6], [v2, HEX.accent1]].forEach(([v, col], j) => {
      const bx = gx + j * 0.72, h = Math.max(0.03, v * H);
      s.addShape(SH.RECTANGLE, { x: bx, y: base - h, w: 0.62, h, fill: { color: col }, line: { color: col }, objectName: `bar-${i}-${j}` });
      tx(s, v.toFixed(2), { x: bx - 0.1, y: base - h - 0.32, w: 0.82, h: 0.3, fontSize: 13, bold: j === 1, color: C.text1, align: "center" });
    });
    tx(s, m, { x: gx - 0.15, y: base + 0.08, w: 1.65, h: 0.3, fontSize: 12, align: "center" });
  });
  table(s, [
    ["기본 AI → RAG 추가", "gpt", "Opus", "Qwen"],
    ["A 급여 기준 · 101", "0.44 → 0.81", "0.47 → 0.91", "0.08 → 0.63"],
    ["A2 추가 규칙 · 38", "0.09 → 0.91", "0.18 → 0.93", "0.03 → 0.58"],
    ["C 환자 판정 · 198", "0.81 → 0.93", "0.82 → 0.98", "0.65 → 0.91"],
    ["D 약 고르기 · 37", "0.32 → 0.43", "0.38 → 0.62", "0.03 → 0.27"],
    ["A형 RAG로 나음 / 못함", "51 / 5", "60 / 5", "68 / 4"],
  ], { x: 6.5, y: 1.75, w: 6.23, colW: [1.9, 1.45, 1.44, 1.44], fontSize: 13, rowH: 0.44 });
  callout(s, [B("가이드북 없이는 최상위 모델도 국내 기준을 모른다 "), P("(A2 0.09~0.18). D형 약 고르기는 RAG를 추가해도 아직 낮다.")], 6.5, 4.6, 6.23, 1.15);
  tx(s, "A형 차이는 세 모델 모두 부호검정 p < 10⁻¹⁰. 1.0 = 만점(맞음 1 · 부분 0.5).", { x: 6.5, y: 5.9, w: 6.23, h: 0.5, fontSize: 11, color: C.accent3 });
  addNote(s);
}

// 5. 기본 AI 오류
{
  const s = content("결과 · 기본 AI", "기본 AI는 국내 기준을 몰랐고, 틀리는 방식은 모델마다 달랐다", SEC[1]);
  const cols = [
    ["gpt-5.6-terra", "외국·예전 기준을 섞었다", ["‘이전 치료’ 오답 10개 모두 TNF 억제제 실패를 언급", "국내 급여가 아닌 Risankizumab 추천 3건", "원문에 없는 조건을 지어낸 답 27(A형)"]],
    ["Claude Opus 5.5", "세부 수치를 잘못 기억했다", ["TNF 혼동은 0", "‘70점 이상 또는 25% 감소’를 ‘그리고’로 기억", "지어낸 덧붙임 34, Risankizumab 3건"]],
    ["Qwen3-14B", "모른다고 답했다", ["A형 오답 93개 중 83개가 ‘가이드북에 적혀 있지 않다’", "약 이름 한글 표기 오류 27(아다리무맙 등)", "해외 약 4(Certolizumab 등)"]],
  ];
  const w = 3.877;
  cols.forEach(([m, head, bs], i) => {
    const x = 0.6 + i * (w + 0.25);
    card(s, x, 1.75, w, 4.15);
    label(s, m, x + 0.3, 1.95, w - 0.6);
    tx(s, head, { x: x + 0.3, y: 2.35, w: w - 0.6, h: 0.5, fontSize: 18, bold: true, color: C.text1 });
    tx(s, bullets(bs, { paraSpaceAfter: 8 }), { x: x + 0.3, y: 3.0, w: w - 0.6, h: 2.8, fontSize: 14 });
  });
  callout(s, [B("한국 고유 기준(유지 평가·이전 치료·처방 기간)은 어느 모델도 기억으로 맞히지 못한다 "), P("→ 근거 문서가 필요한 이유")], 0.6, 6.05, 12.13, 0.8);
  addNote(s);
}

// 6. RAG 추가 후 오류
pres.addSection({ title: SEC[2] });
{
  const s = content("오류 분석 · RAG 추가", "좋은 모델일수록 남은 오답은 검색 문제였다", SEC[2]);
  tx(s, "RAG 추가 후 A형에서 잃은 점수 (101점 중)", { x: 0.6, y: 1.65, w: 7.6, h: 0.35, fontSize: 14, bold: true, color: C.text1 });
  table(s, [
    ["원인", "gpt", "Opus", "Qwen"],
    ["검색 · 근거 쪽을 못 가져옴", "6.0", "7.0", "6.5"],
    ["읽기 · 같은 쪽의 다른 기준을 옮김", "5.0", "0", "13.0"],
    ["답변 · 조건 축약 (금기·내약성 생략)", "7.5", "0", "9.5"],
    ["그 밖의 답변·읽기", "1.0", "2.0", "8.0"],
    ["합계", "19.5", "9.0", "37.0"],
  ], { x: 0.6, y: 2.05, w: 7.6, colW: [4.6, 1.0, 1.0, 1.0], fontSize: 14, rowH: 0.48 });
  tx(s, "세 모델은 같은 5쪽을 받았다 → 검색으로 잃은 점수가 같다. 차이는 읽고 답하는 단계에서 난다. 분류는 코드 규칙이며 손 분류와 28건 중 27건 일치.", { x: 0.6, y: 5.1, w: 7.6, h: 0.8, fontSize: 12, color: C.accent3 });
  card(s, 8.45, 1.65, 4.28, 5.15, "E3ECF3");
  label(s, "세 모델이 모두 틀린 문항", 8.73, 1.85, 3.8);
  tx(s, "A 7 · A2 4 · C 5 · D 14", { x: 8.73, y: 2.25, w: 3.8, h: 0.55, fontSize: 22, bold: true, color: C.accent1, fontFace: "Arial" });
  tx(s, bullets([
    "모두 ‘근거 쪽을 못 가져옴’",
    "검사 수치가 적힌 체크리스트 쪽",
    "정맥주사 고시 쪽 대신 피하주사 쪽",
    "처방 기간이 적힌 투약간격 쪽",
    "D형은 약이 많아 5쪽에 다 안 들어옴",
  ], { paraSpaceAfter: 6 }), { x: 8.73, y: 2.95, w: 3.8, h: 3.7, fontSize: 14 });
  addNote(s);
}

// 7. 안전
{
  const s = content("오류 분석 · 안전", "위험한 오답은 RAG를 추가했을 때 생겼고, 원인은 하나였다", SEC[2]);
  card(s, 0.6, 1.75, 6.9, 2.75);
  label(s, "예 · ANC 900 환자에게 Filgotinib (정답 ‘아니오’)", 0.9, 1.92, 6.4);
  tx(s, [B("기본 AI: "), P("“ANC 1,000 미만이라 안 된다” → 맞음 (허가사항이라 기억함)")], { x: 0.9, y: 2.4, w: 6.4, h: 0.7, fontSize: 15 });
  tx(s, [B("RAG 추가: "), P("“발췌에는 이 수치 기준이 없다” → ‘예’ (허용). 기준이 적힌 체크리스트 p.49가 5쪽 안에 없었다")], { x: 0.9, y: 3.15, w: 6.4, h: 1.2, fontSize: 15 });
  table(s, [
    ["‘높음 · 안전’ 오답 문항 (C / D)", "기본 AI", "RAG 추가"],
    ["gpt-5.6-terra", "1 / 3", "5 / 6"],
    ["Claude Opus 5.5", "4 / 3", "1 / 6"],
    ["Qwen3-14B", "8 / 2", "6 / 6"],
  ], { x: 0.6, y: 4.7, w: 6.9, colW: [3.5, 1.7, 1.7], fontSize: 14, rowH: 0.45 });
  card(s, 7.75, 1.75, 4.98, 2.75, "F6E8D8");
  label(s, "세 모델이 같은 6문항", 8.05, 1.92, 4.4, C.accent4);
  tx(s, "Hb 7.5 · ANC 900 · ALC 450 환자에게 Upadacitinib을 넣었다. 모델을 바꿔도 남는다 → 모델이 아니라 검색 구조(체크리스트 쪽 누락) 문제", { x: 8.05, y: 2.4, w: 4.4, h: 2.0, fontSize: 15 });
  card(s, 7.75, 4.7, 4.98, 1.8, "E3ECF3");
  label(s, "고칠 수 있다", 8.05, 4.87, 4.4);
  tx(s, "고시 쪽에 체크리스트 쪽을 자동으로 붙이면 안전 오답 11건 모두 근거 쪽이 들어온다 (시뮬레이션, 답은 아직 다시 안 받음)", { x: 8.05, y: 5.27, w: 4.4, h: 1.15, fontSize: 14 });
  addNote(s);
}

// 8. 개선
pres.addSection({ title: SEC[3] });
{
  const s = content("개선 방향", "정확도를 올리려면: 검색 → 답 지시문 → D형 규칙", SEC[3]);
  const st = [
    ["1 · 검색", "딸린 쪽 자동 첨부", "고시 쪽을 찾으면 같은 약의 체크리스트·투약간격 쪽도 붙인다", "안전 오답 11, 세 모델 공통 오답", "E3ECF3"],
    ["2 · 검색", "약·제형별로 찾기", "질문의 약·주사 형태로 고시 쪽을 붙이고, D형은 약마다 따로 검색", "IV/SC 혼동, D형 빠뜨린 약", "E3ECF3"],
    ["3 · 답변", "답 지시문 다듬기", "‘조건을 빠짐없이’, ‘시작 기준과 지속 기준 구분’, 근거 없으면 ‘판단 불가’", "축약 15~17, 다른 기준 5~13", null],
    ["4 · 판정", "D형은 규칙으로", "AI는 환자 정보만 뽑고, 급여 판정은 코드가 한다", "여러 약 고르기 전체", null],
  ];
  const w = 2.9;
  st.forEach(([lab, head, body, tgt, fill], i) => {
    const x = 0.6 + i * (w + 0.177);
    card(s, x, 1.75, w, 3.85, fill);
    label(s, lab, x + 0.25, 1.95, w - 0.5);
    tx(s, head, { x: x + 0.25, y: 2.35, w: w - 0.5, h: 0.5, fontSize: 17, bold: true, color: C.text1 });
    tx(s, body, { x: x + 0.25, y: 2.95, w: w - 0.5, h: 1.6, fontSize: 13 });
    tx(s, [B("겨냥: "), P(tgt)], { x: x + 0.25, y: 4.6, w: w - 0.5, h: 0.9, fontSize: 12, color: C.accent3 });
  });
  callout(s, [B("기대: "), P("1·2만으로 A형 최대 +0.06~0.07(세 모델 모두). 답을 다시 받아야 확인되고, 이번 오답을 보고 만든 개선이라 사후 분석으로 보고한다.")], 0.6, 5.8, 12.13, 0.95);
  addNote(s);
}

// 9. 한계와 다음 단계
{
  const s = content("한계와 다음 단계", "결과를 믿을 수 있게 만드는 것이 먼저다", SEC[3]);
  card(s, 0.6, 1.75, 5.94, 4.95);
  label(s, "한계", 0.9, 1.95, 5.3, C.accent4);
  tx(s, bullets([
    "임상의 검증 0건: 문항·채점·오류 분류·위험도 기준",
    "답 1회 · 채점 1회 (다시 물으면 판정이 바뀌는 문항 있음)",
    "AI 채점자 하나(OpenAI). 다만 Claude 답이 더 높게 나와 봐주기 증거는 없음",
    "Opus·Qwen은 gpt가 찾은 쪽을 받음 → 검색 능력 차이는 안 봄",
    "2024 가이드북 한 판",
  ], { paraSpaceAfter: 8 }), { x: 0.9, y: 2.4, w: 5.35, h: 4.2, fontSize: 15 });
  table(s, [
    ["#", "다음 단계", "API 비용"],
    ["1", "임상의 2인 검수 (검수표 준비됨)", "없음"],
    ["2", "안전 오답 11문항 재질문 (체크리스트 쪽 붙여서)", "수천 원"],
    ["3", "반복 측정 (답 3회 · 채점 3회) → 채점자 κ", "약 $10~20"],
    ["4", "검색 개선 · 정답 쪽 직접 제공 실험", "약 $4~6+"],
  ], { x: 6.79, y: 1.75, w: 5.94, colW: [0.5, 3.94, 1.5], fontSize: 13, rowH: 0.62 });
  tx(s, "API는 연구자가 승인할 때만, 배치(요금 절반)로. 지금까지 누적 약 $45~56.", { x: 6.79, y: 5.0, w: 5.94, h: 0.6, fontSize: 12, color: C.accent3 });
  addNote(s);
}

// 10. 논의
{
  const s = content("논의", "오늘 정하고 싶은 것", SEC[3]);
  const ds = [
    ["01 · 임상의 검수", "검수자 2인과 일정. 검수표(문항 380 + 결정 20)와 요청문 초안은 준비됨", null],
    ["02 · 기준 확인", "65세 이상 JAK 조항을 ‘안전’으로 볼지 ‘삭감’으로 볼지. D형에서 철자만 다른 약 이름을 정답으로 볼지", null],
    ["03 · 다음 실험 순서", [B("제안: "), P("안전 오답 재질문(수천 원) → 반복 측정(약 $10~20) → 검색 개선")], "E3ECF3"],
    ["04 · 투고 방향", "목표 학술지를 정하면 보고 지침(예: TRIPOD-LLM)에 맞춰 원고 준비", null],
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
