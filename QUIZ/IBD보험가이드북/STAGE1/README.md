# STAGE1 — IBD 보험가이드북 급여 기준 평가

> 2026-11-16 기준. 2026-11-15판은 `_archive/README_STAGE1_20261115.md`, 2026-10-27판 README는 `_archive/README_STAGE1_20261027.md`에 보관했다. 그때 설명한 v1 채점과 `human_check.csv`는 지금 결과에 쓰지 않는다(7절).

## 한눈에

**질문:** 같은 모델(`gpt-5.6-terra`)에 2024 대한장연구학회 보험가이드북 발췌를 붙이면, 국내 급여 기준 답이 얼마나 정확해지는가. 다른 모델(Claude Opus 5.5, 내 Mac의 공개 모델)로도 같은 결론인지 확인한다(5b절).

| 평가 대상 | 내용 |
| --- | --- |
| 기본 AI (`llm`) | `gpt-5.6-terra`. 가이드북 없이 "2024 보험가이드북 기준으로 답하라"는 지시와 질문만 |
| RAG 에이전트 (`agent`) | 같은 모델 + 검색으로 고른 가이드북 상위 5쪽. BM25·임베딩 각 12 → RRF(≤20) → bge-reranker-v2-m3 → 상위 5 |

| 유형 | 문항 | 묻는 것 | 정답 | 채점 |
| --- | --- | --- | --- | --- |
| A | 107 (본 점수 101) | 약별 급여 기준 단답 | CSV에서 코드 | LLM 채점자 v2.1 |
| A2 | 38 | 재투여·처방 기간·용량 증량·교체투여 등 추가 규칙 | CSV 메모에서 코드 | LLM 채점자 v2.1(+A2) |
| C | 198 | 환자 사례: 급여 예 / 아니오 / 판단 불가 | A형 열쇠로 코드 판정 | 코드 |
| D | 37 | 보기 없이 급여 가능한 생물학제제·소분자제제 모두 | 9개 성분 대입 코드 계산 | 코드 |

문항과 정답은 모두 코드가 `data/IBD보험가이드북.csv`(44행)에서 만든다. LLM은 문항을 만들지 않는다.

**API를 쓰는 단계:** 답 받기(`eval_a.py` gpt-5.6-terra, `eval_claude_batch.py` Claude)와 A·A2형 채점(`regrade_v2.py`·`regrade_v2_batch.py`, gpt-6-sol). 나머지는 모두 API 없이 돈다(내 Mac의 공개 모델 `eval_local_mlx.py`도 요금 없음). API 단계는 연구자가 실행을 승인할 때만 돌리고, 돌리기 전에 호출 수·비용을 보고한다. 2026-11-16부터 새 실험은 **배치 API**(요금 절반, 요청 내용은 일반 호출과 같음)로 돌린다.

## 실행 순서 (`IBD보험가이드북` 폴더에서)

```bash
# 1) 문항 (API 없음)
python3 STAGE1/make_a.py && python3 STAGE1/make_a2.py && python3 STAGE1/make_c.py && python3 STAGE1/make_d.py
# 2) 답 받기 (API). 에이전트는 Docker 백엔드(ibdrxagent-backend-1, 포트 8001)를 켠 뒤
AGENT=http://127.0.0.1:8001/api/guide/ask
python3 STAGE1/eval_a.py --target llm --items STAGE1/output/c_items.jsonl --run c_llm_gpt-5.6-terra
python3 STAGE1/eval_a.py --target agent --agent-url $AGENT --agent-reply-key answer --items STAGE1/output/c_items.jsonl --run c_agent_gpt-5.6-terra --workers 1
# 3) 채점: A·A2형은 v2.1 채점자(API), C·D형은 코드(API 없음)
python3 STAGE1/regrade_v2.py --run agent_gpt-5.6-terra --repeat 3
python3 STAGE1/score_cases.py --run c_agent_gpt-5.6-terra --items STAGE1/output/c_items.jsonl
# 4) 분석 (API 없음)
python3 STAGE1/analyze_errors.py && python3 STAGE1/simulate_retrieval.py && python3 STAGE1/sensitivity_additions.py
```

유형별 전체 명령은 `RUN_PLAN.md`에 있다. 실행 폴더 이름은 `<유형>_<대상>_gpt-5.6-terra`이고, A형만 유형 접두사가 없다(`llm_gpt-5.6-terra`, `agent_gpt-5.6-terra`).

## 1. 문항 만들기 (API 없음)

| 스크립트 | 결과 (`output/`) |
| --- | --- |
| `make_a.py` | `a_items.jsonl`, `a_review.csv`, `summary.json` |
| `make_a2.py` | `a2_items.jsonl`, `a2_summary.json` (약 이름 규칙은 `make_a.py`에서 가져옴) |
| `make_c.py` | `c_items.jsonl`, `c_summary.json` |
| `make_d.py` | `d_items.jsonl`, `d_summary.json`, `d_review.md` (+ 평가에 쓰지 않는 보기형 `d_options_items.jsonl`) |

- **A2형:** CSV 메모(notes)에서 R 재투여 · P 교체·처방 · T 혈중농도 검사 · W 교체투여(스위치) · L 처방 기간 · J 자가주사 일지 · D 용량 증량 영역을 뽑는다. 약과 무관한 일반 규칙은 '일반' 문항 1개로만 만든다.
- **C형:** 약·적응증 25행마다 모든 조건을 만족하는 기본 환자를 만들고 조건을 하나씩 깬다. 경계값(CDAI 220 인정 / 219 불인정)과 함정 18문항(비-TNF 약에 TNF 실패 불필요, 약마다 다른 Hb 하한, 고령 조항 없는 약)을 둔다.
- **D형:** 환자를 가이드북의 9개 성분에 하나씩 대입해 정답 집합을 계산한다. 보기를 주지 않아 해외 허가 약·이미 실패한 약을 쓰는지도 본다.

### A형 상세
A형은 "이 약은 어떤 기준이면 급여되나"를 묻는 **서술형 단답** 문항이다. 보기는 주지 않는다. C형(환자에게 적용)과 짝을 이룬다.

| | 문항 | 정답 |
|---|---|---|
| A형 | [Adalimumab, 성인 크론병] 급여 활성도 기준은? | CDAI 220 이상 |
| C형 | CDAI 219인 40세 크론병 환자, 아달리무맙 급여? | 불가 |

A는 맞히고 C를 틀리면 기준은 아는데 적용을 못 한 것, A부터 틀리면 기준을 모르는 것이다.

#### 실행

`IBD보험가이드북` 폴더에서:

```bash
python3 STAGE1/make_a.py
```

- 이 파일 하나로 돈다. 파이썬만 있으면 되고 모델(API)은 쓰지 않는다
- CSV는 `IBD Rx Agent/data/IBD보험가이드북.csv`를 읽는다. 다른 파일은 `--csv 경로`
- 실행할 때마다 자체 시험(아래)을 먼저 돌리고, 통과해야 문항을 쓴다

#### 문항 (지금 CSV 기준 107문항, 고유 정답 52개)

| 기준 | 수 | 질문 예 | 정답 예 | 정답을 꺼내는 칸 |
|---|---|---|---|---|
| 나이 | 7 | [Infliximab IV, 장형 베체트] 가이드북에 적힌 연령(체중) 조건은? | 19세 이상 | 원문에 나이가 적힌 6행 + 대조 1행(ADA 베체트: "연령 조건은 가이드북에 적혀 있지 않다") |
| 활성도 | 25 | [Adalimumab, 궤양성 대장염] 급여 활성도 기준은? | Mayo 6~12 그리고 내시경 subscore 2 이상 | activity_scale, activity_threshold |
| 이전 치료 | 25 | [Infliximab IV, 누공성 크론병] 어떤 이전 치료에 실패해야 급여되는가? | 보편적 치료(2가지 이상의 치료법: 항생제·배출법·면역억제 치료 등)에 반응이 없는 경우 | 원문 구절 그대로 |
| 고령·고위험 | 7 | [Tofacitinib, 궤양성 대장염] 65세 이상 환자에게 쓸 때 붙는 추가 급여 조건이 있는가? | (원문) 65세 이상/심혈관계 고위험군/악성 종양 위험 환자는 … 생물학제제에 적절히 반응하지 않거나 내약성이 없는 경우에 한하여 | JAK 4행 + 대조 3행(OZA·VEDO UC·UST CD: "가이드북에 적혀 있지 않다") |
| 검사 하한 | 12 | [Filgotinib, 궤양성 대장염] ANC 하한은? | 1×10⁹/L (= 1,000 cells/mm³) | lab_* (원문 단위 그대로) |
| 금기 | 6 | [Ozanimod, 궤양성 대장염] 가이드북의 투여 전 체크리스트 항목을 모두 쓰시오. | ECG 금기 없음, …, 과민반응 없음 (항목을 직접 나열) | 체크리스트가 있으면 그 항목 그대로(※ 주의 문구·★ 메모 제외), 없으면 금기 칸 |
| 유지 기준 | 25 | [Ustekinumab, 크론병] 유지요법은 언제, 어떤 조건에서 인정되는가? | 첫 투약 후 16-20주 평가, CDAI 70점 이상 감소 또는 25% 이상 감소 | eval_week, eval_criteria |

- 약 이름은 성분·질환이 기본이다. 같은 성분에 경로가 여럿이면(IFX, VEDO) 경로를, 같은 성분·경로·질환에 다른 연령군 행이 있으면 연령군을 붙인다. 그래서 "성인 장형 베체트"처럼 이름이 나이 정답을 알려 주지 않는다.
- "없다"가 정답인 대조 문항(나이 1, 고령·고위험 3, 활성도 점수 기준 4: 누공성 크론병 2·장형 베체트 2)을 넣어, "있다"로만 답하거나 기준을 지어내는 편향을 잡는다. CSV의 N·빈칸은 "아니다"가 아니라 "…은 가이드북에 적혀 있지 않다"로 쓰고, 이 문장은 코드 한 곳(`not_written`)에서만 만든다.
- 정답에 넣지 않는 것: CSV를 옮긴 사람의 메모(`(★…)`), 체크리스트 아래 ※ 주의 문구(채점 열쇠의 `참고(필수 아님)`으로만 둠), 평가방법 소제목('누공이 없는 경우' → `함께 써도 정답`).
- 평가 시점이 원문끼리 다른 3행(VEDO SC 2행, OZA — notes의 [원문 상이])은 시점을 묻지 않는다.
- 용량·이상반응·기전처럼 급여 판정에 쓰지 않는 칸은 묻지 않는다.

#### 채점 열쇠

문항마다 `answer.채점`에 코드나 LLM 채점자가 쓸 구조를 둔다.

| 기준 | 열쇠 |
|---|---|
| 활성도 | 척도, 값, 비교(이상/초과), Mayo 범위·결합(그리고)·내시경, 함께 써도 정답(누공 없는 경우) |
| 이전 치료 | 최소 가지 수(2 또는 없음), 치료 목록, 반응 조항(반응 없음 / ·불내성·금기 / ·부작용 중단) |
| 고령·고위험 | 조항 있음/없음, 대상, 조건 |
| 검사 하한 | 값(cells/mm³ 또는 g/dL로 환산), 단위, 비교 |
| 나이 | min, max, 체중초과, 함께 써도 정답인 값 |
| 금기 | 항목 목록, 참고(필수 아님: ※ 문구) |
| 유지 기준 | 절대 감소, 상대 감소(%), 결합(또는/그리고), 직장출혈 조건, 시점 |

서술형 답을 어떻게 맞다고 볼지(동의어, '등' 목록은 일부만 써도 되는지, 괄호 속 세부까지 요구하는지)는 채점 단계에서 정한다.

#### 원문 대조와 자체 시험

정답은 원문 칸에 적힌 그대로 따른다. **기본값은 없다.** 아래 중 하나라도 걸리면 문항을 쓰지 않고 멈춘다.

- 숫자·이상/초과·그리고/또는을 못 읽거나 두 가지로 읽힘
- 칸끼리 맞지 않음: 평가 시점(eval_week) ↔ 평가 기준 문장, 활성도 칸 ↔ prior_bio_note의 "2가지", 금기 칸(Y) ↔ 체크리스트, 나이 표 ↔ 원문 문구와 age_min·age_max
- 원문에는 기준이 있는데 판정 칸이 비어 문항이 빠질 상황 (activity_scale·prior_conventional·prior_biologic 비어 있음, 심전도 칸 Y인데 금기 내용 없음)
- 검사 하한의 경계 방향(미만 시/이하 시)이 없음

실행할 때마다 CSV를 일부러 바꾸거나 정답을 검사하는 시험 33건을 먼저 돌려, 멈추거나 바뀐 원문을 그대로 따르는지, 정답에 들어가면 안 되는 말이 없는지 확인한다(예: CDAI ≥→>, PUCAI 초과→이상, Mayo and→or, 유지 기준 또는→그리고, 직장출혈 1점→2점, Hb 값 두 개, 평가 시점 불일치, 체크리스트에 ★ 메모·※ 문구 없음, 괄호 밖 ★ 메모는 멈춤). 바꿀 문자열이 지금 CSV에 없으면 그 시험은 "건너뜀"으로 알리고 생성은 막지 않는다.

#### 결과 (`STAGE1/output/`)

| 파일 | 내용 |
|---|---|
| `a_items.jsonl` | 문항. `짝키`(약\|기준)로 다음 단계 C·E형과 잇는다 |
| `a_review.csv` | 검수 양식 (엑셀). 판정·수정 정답·검수자·코멘트 칸을 채운다 |
| `summary.json` | 기준별·형식별·약 계열별 개수, 고유 정답 수, 자체 시험 결과, CSV 해시 |

**한계:** CSV가 가이드북 원문과 같다고 가정한다(원문 PDF와의 대조는 사람 검수). 논문에는 문항 수와 함께 고유 정답 수(52)도 보고한다.

## 2. 답 받기 (`eval_a.py`, API: gpt-5.6-terra)

- **키:** `IBD보험가이드북/.env` → `STAGE1/.env` → `data/RAG/.env` 순으로 `OPENAI_API_KEY`를 찾는다(`env.example` 참고). 키 값은 화면에 출력하지 않는다.
- **에이전트:** `--agent-url .../api/guide/ask --agent-reply-key answer`. 요청 모양은 `agent_payload.json`(`answer_only: true`). 처음에는 `--agent-ping`으로 1문항만 보내 응답 모양을 본다. 에이전트는 `--workers 1`.
- **답 형식(두 대상 같음):** A·A2형 `답: …` / C형 `판정: 예·아니오·판단 불가` + `이유:` / D형 `인정: 성분명, …` + `이유:`. C·D형은 기본 AI에 `CASE_FORMAT`, 에이전트에 백엔드 `answer_style`로 같은 문장을 준다.
- **이어서 받기:** 저장된 답은 다시 부르지 않는다. 먼저 `--limit 2`로 형식을 확인한다. `--fresh`는 그 실행 폴더 전체를 지운다.
- **질문이 바뀐 문항:** `--redo-ids <json>`이 그 문항의 옛 답·채점을 `superseded_*.jsonl`로 옮기고 다시 받는다. 지우지 않는다.
- 답에는 받은 시점의 질문(`질문`)이 함께 저장되고, 채점 스크립트는 지금 질문과 다른 질문의 답을 채점하지 않는다.
- 기본 단계는 `--phase baseline`(답만 받기)이다. 예전 v1 채점은 `--phase judge`를 명시해야만 돈다(7절).

## 3. 채점

### A·A2형: `regrade_v2.py` (LLM 채점자 v2.1, gpt-6-sol)

- 채점자가 받는 것: 질문, 정답, 채점 열쇠, 그 문항의 가이드북 원문 쪽, 척도 범위(Mayo 0~12 등), 채점할 답. 답이 어느 대상의 것인지는 모른다.
- 판정: 맞음 / 부분 / 틀림과 요소별 판정. 원문에 없는 덧붙임은 '덧붙인 내용'에 원문에 있음/없음으로 따로 기록한다.
- v2.1 규칙(2026-11-10 확정): 평가 시점만 틀리면 부분 · 결과를 밝힌 여집합 표현('N 미만이면 투여 불가')은 맞음 · '함께 써도 정답'은 있든 없든 감점 없음.
- A2형은 같은 프롬프트에 'A2형 열쇠 읽는 법' 3줄만 덧붙인다(채점 버전 `v2.1+A2`).
- `--repeat 3` → `graded_v21.jsonl`, `graded_v21_r1.jsonl`, `graded_v21_r2.jsonl`. `--dry-run`은 API 없이 프롬프트만 점검한다. `--regrade-ids`는 채점 열쇠만 바뀐 문항의 옛 채점을 `superseded_*`로 옮기고 다시 채점한다.
- **점수:** 맞음 1 · 부분 0.5 · 틀림 0의 평균. A형 본 점수는 금기 6문항을 뺀 101문항.

### C·D형: `score_cases.py` (코드, API 없음)

- C형: `판정:` 줄을 정답과 비교. 못 읽으면 형식 오류(틀림).
- D형: `인정:` 줄의 약 집합을 정답 집합과 비교(완전 일치, 재현율, 정밀도). 가이드북에 없는 약, 이미 실패한 약 재사용, 알아보지 못한 이름은 따로 센다.
- 결과: `graded_code.jsonl`, `summary_code.json`.

### 지금 보고하는 점수와 반복 채점 현황 (2026-11-15)

- 보고 점수는 `graded_v21.jsonl`(채점 1회분)에서 계산한다. 답은 1회 측정이다.
- A형 본 점수 101문항 중 74문항은 3회 채점이 있다. 3회 판정이 모두 같은 문항: 기본 AI 71/74, 에이전트 74/74. 3회 다수결로 바꿔도 본 점수는 기본 AI 0.441 → 0.436, 에이전트 0.807 → 0.807.
- 2026-11-12에 고친 A형 27문항(본 점수 기준)과 A2형 38문항은 아직 채점 1회뿐이다. 반복 측정 때 함께 맞춘다.

## 4. 검수표 (API 없음)

| 스크립트 | 사용 | 결과 |
| --- | --- | --- |
| `make_review_xlsx.py` | `python3 STAGE1/make_review_xlsx.py STAGE1 STAGE1/output/검수표_임상의.xlsx` | 임상의 문항 검수표(380행 + 결정 20행). 모델 답은 넣지 않는다 |
| `make_csv_review.py` | `python3 STAGE1/make_csv_review.py STAGE1 <가이드북.pdf> <out.xlsx>` | CSV ↔ PDF 원문 대조표 (openpyxl, pypdf 필요) |
| `make_judge_check.py` | `build --runs … --items … --out … --key …` / `score <key.json> <임상의1.xlsx> [<임상의2.xlsx>]` | 채점자 검증표(눈가림)와 사람–채점자 κ. 아직 실행 전 |

`make_judge_check.py`의 key 파일(채점자 판정)은 임상의에게 주지 않는다.

## 5. 분석 (API 없음, 저장된 결과만 사용)

| 스크립트 | 하는 일 | 결과 (`eval_out/`) |
| --- | --- | --- |
| `analyze_errors.py` | 에이전트 오답·부분 70문항이 근거 '핵심 쪽'을 검색해 왔는지 분류 | `error_taxonomy_agent.json` (보고서 `오답원인분류_에이전트.md`) |
| `simulate_retrieval.py` | 가져온 5쪽에 규칙 A(딸린 쪽)·B(질문 라우팅)로 쪽을 붙였을 때 근거 쪽 포함률과 발췌 길이 | `simulate_retrieval.json` |
| `sensitivity_additions.py` | '원문에 없는 덧붙임은 틀림' 규칙을 좁게·넓게 끈 민감도 | `sensitivity_additions.json` |
| `quote_check.py` | A·A2형 답을 가이드북 원문과 글자 단위로 비교: 원문 일치도, 조건 누락(내약성·금기 등) | `quote_check.json` (보고서 `인용문원문대조.md`) |
| `risk_analysis.py` | C·D형 오답의 방향과 위험도(안전 / 삭감 / 지연 / 보류). 기준은 연구자 초안 | `risk_analysis.json` (보고서 `오답위험도.md`) |

검색 시뮬레이션은 답을 다시 받지 않으므로 '근거 쪽이 들어온다'까지만 보여 준다. 오답 원인 분류는 Claude가 했고 임상의 검수 전이다.

## 5b. 다른 모델로 확인 · 배치 API (2026-11-16)

같은 문항·같은 지시문으로 답하는 모델만 바꾼다. 에이전트는 새로 검색하지 않고 `gpt-5.6-terra` 에이전트가 가져온 5쪽(`agent_gpt-5.6-terra` 등의 `응답.sources`)을 그대로 넣는다. 지시문은 `eval_a.py`·`backend/app/rag/generate.py`에서 import해서 쓴다(글자까지 같음).

| 스크립트 | 하는 일 | API · 실행 환경 | 결과 |
| --- | --- | --- | --- |
| `eval_claude_batch.py` | Claude 답 받기: `build`(요청 파일만, 무료) → `submit --yes`(과금) → `status` → `fetch` | Anthropic Message Batches · `.venv_claude` | `eval_out/<유형>_<대상>_claude-opus-5-5/answers.jsonl`, 요청·원본·실측 비용 `eval_out/claude_batch/<tag>/` |
| `regrade_v2_batch.py` | `regrade_v2.py`와 같은 v2.1 채점을 배치로: `build --job run:items` → `submit --yes` → `status` → `fetch` | OpenAI Batch · gpt-6-sol · `.venv_claude` | `graded_v21.jsonl`(regrade_v2와 같은 모양), `eval_out/openai_batch/<tag>/` |
| `eval_local_mlx.py` | 내 Mac(Apple 칩)에서 공개 모델로 답 받기. 기본 `mlx-community/Qwen3-14B-4bit` | 요금 없음 · `.venv_mlx`(mlx-lm) | `eval_out/<유형>_<대상>_qwen3-14b-4bit/`, 실행 기록 `eval_out/local_mlx/` |
| `compare_models.py` | 모델별 정확도·짝 비교·안전 오답 표 | 없음 | `eval_out/모델비교.md` |
| `findings_by_model.py` | gpt로 정리한 발견(기준 혼동·축약·빠뜨린 약·안전 오답)을 같은 규칙으로 모델마다 계산. gpt 값이 기존 보고서와 같게 나와야 한다 | 없음 | `eval_out/모델별발견.json`·`.md` |

```bash
cd STAGE1
.venv_claude/bin/python eval_claude_batch.py build --tag full --dry      # 개수·예상 비용만 (무료)
.venv_claude/bin/python eval_claude_batch.py fetch --tag full            # 끝난 배치 결과 받기 (무료)
.venv_claude/bin/python regrade_v2_batch.py build --job agent_claude-opus-5-5:output/a_items.jsonl --dry
.venv_mlx/bin/python eval_local_mlx.py --types C D --limit 5 --think on  # 내 Mac 파일럿
python3 compare_models.py && python3 findings_by_model.py                 # 비교표 (무료)
```

- 키: `STAGE1/.env`의 `ANTHROPIC_API_KEY`, OpenAI 키는 기존과 같다(`eval_a.load_env`).
- 실행 환경: `.venv_claude`(anthropic·openai SDK), `.venv_mlx`(mlx-lm). 기존 스크립트는 시스템 `python3`로 그대로 돈다.
- 첫 판(Claude C·D형만)은 `_archive/eval_claude_batch_CD_only_20261116.py`.

## 6. 결과 파일 (`eval_out/<실행>/`)

| 파일 | 내용 |
| --- | --- |
| `answers.jsonl` | 받은 답, 답을 받을 때의 모델·질문·시각. 에이전트는 응답 전체(`응답.sources`의 쪽 번호 포함) |
| `graded_v21.jsonl`, `_r1`, `_r2` | A·A2형 v2.1 채점 (주 결과는 `graded_v21.jsonl`) |
| `graded_code.jsonl`, `summary_code.json` | C·D형 코드 채점 |
| `superseded_*.jsonl` | 문항을 고치기 전의 답·채점. 예전 결과 재현용으로 보존 |
| `graded.jsonl`, `graded_v2*.jsonl`, `results.csv`, `summary.json`, `human_check.csv` | 예전 v1·v2 채점 결과 (지금 결과에 쓰지 않음) |
| `claude_review_NOT_human.csv` | v1 판정을 Claude가 검토한 것. 사람 판정이 아니므로 기준 정답으로 쓰지 않는다 (`eval_out/README_판정주체.md`) |

그 밖의 실행 폴더: `d_options_*`(보기형 D형, 평가에 쓰지 않음), `evolve_smoke`(자기진화 시험 실행), `*_claude-opus-5-5`·`*_qwen3-14b-4bit`(다른 모델, 5b절), `claude_batch/`·`openai_batch/`(배치 요청·원본 결과·실측 비용), `local_mlx/`(내 Mac 실행 기록).

## 7. 예전 방식과 보관 (재현용으로 남겨 둠)

- **v1 채점 (`eval_a.py --phase judge`):** 채점자가 원문을 못 보는 방식. 2026-10-27 첫 결과에 썼고, 지금은 v2.1로 바꿨다. 예전 결과를 다시 만들 수 있게 코드는 지우지 않았다. `human_check.csv`(v1 기준 표본)도 쓰지 않는다. 사람 검증은 `make_judge_check.py`로 새로 한다.
- **보기형 D형 (`d_options`):** `make_d.py`가 함께 만들고 `score_cases.py`가 채점할 수 있지만 평가에는 쓰지 않는다.
- **자기진화 실험 (`evolve/`):** 경험 노트(playbook)를 에이전트 프롬프트에 붙이는 실험. 2026-11-10 시험 실행까지만 했다. `evolve/split.json`은 A형 내용 묶음 30개를 두 묶음(16·14)으로 나눈 것으로 이 실험에만 쓴다. 묶음 자체는 코드가 계산한다(평가 시점을 뺀 채점 열쇠가 같은 문항, `evolve.py`와 `make_review_xlsx.py`에 같은 규칙).
- **문항 수정 이력:** 고치기 전 문항은 `output/_backup_<날짜>/`, 고치기 전 답·채점은 `eval_out/<실행>/superseded_*.jsonl`.
- **`_archive/`:** 더 쓰지 않는 스크립트와 예전 시험 결과. 2026-11-10 채점 비교를 다시 만드는 방법도 `_archive/README.md`에 있다(2026-11-15 확인: 저장된 결과와 같음).
