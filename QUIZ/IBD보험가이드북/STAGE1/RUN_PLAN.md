# 다음 실행 계획 (2026-11-12 문항 기준)

> OpenAI API(연구자 키)를 쓰는 단계다. **연구자가 '돌려'라고 할 때만** 실행하고, 실행 전에 호출 수·비용을 다시 보고한다.
> RAG 에이전트 단계는 Docker 백엔드(`ibdrxagent-backend-1`)를 켜야 한다(켜기 전에 연구자 허락).

## 무엇을 하나

| 단계 | 문항 | 기본 AI 답 | 에이전트 답 | 채점 |
| --- | --- | --- | --- | --- |
| A형 질문이 바뀐 문항 다시 받기 | 24 (`output/redo_ids_20261112.json`) | 24 | 24 | v2.1 × 3회 = 144 |
| A형 채점 열쇠만 바뀐 문항 다시 채점 | 7 (`output/regrade_ids_20261112.json`) | – | – | 7 × 2 × 3 = 42 |
| A2형 첫 실행 | 38 | 38 | 38 | v2.1 × 3회 = 228 |
| C형 첫 실행 | 198 | 198 | 198 | 코드 채점 (API 없음) |
| D형 첫 실행 | 37 | 37 | 37 | 코드 채점 (API 없음). 제외 이유는 채점하지 않음 |
| 합계 | | 297 (gpt-5.6-terra) | 297 (gpt-5.6-terra) | 414 (gpt-6-sol) |

예상 비용(대략): 기본 AI $0.6~1.8 + 에이전트 $3~6 + 채점 $8~12 = **약 $12~20**. 에이전트는 요청을 하나씩 처리해 약 3~6시간.

## 명령 (IBD보험가이드북 폴더에서)

```bash
AGENT=http://127.0.0.1:8001/api/guide/ask
# 1) A형: 바뀐 질문 다시 받기 (예전 답·채점은 superseded_*.jsonl로 옮겨짐)
python3 STAGE1/eval_a.py --target llm --run llm_gpt-5.6-terra --redo-ids STAGE1/output/redo_ids_20261112.json
python3 STAGE1/eval_a.py --target agent --agent-url $AGENT --agent-reply-key answer --run agent_gpt-5.6-terra --workers 1 --redo-ids STAGE1/output/redo_ids_20261112.json
# 2) A형 채점 (v2.1, 3회): 다시 받은 24문항 + 열쇠만 바뀐 7문항
python3 STAGE1/regrade_v2.py --run llm_gpt-5.6-terra --repeat 3 --regrade-ids STAGE1/output/regrade_ids_20261112.json
python3 STAGE1/regrade_v2.py --run agent_gpt-5.6-terra --repeat 3 --regrade-ids STAGE1/output/regrade_ids_20261112.json
# (11-12 이후 이 비교는 11-10 상태 복원이 필요: STAGE1/_archive/README.md 참고)
# 3) A2형
python3 STAGE1/eval_a.py --target llm --items STAGE1/output/a2_items.jsonl --run a2_llm_gpt-5.6-terra
python3 STAGE1/eval_a.py --target agent --agent-url $AGENT --agent-reply-key answer --items STAGE1/output/a2_items.jsonl --run a2_agent_gpt-5.6-terra --workers 1
python3 STAGE1/regrade_v2.py --run a2_llm_gpt-5.6-terra --items STAGE1/output/a2_items.jsonl --repeat 3
python3 STAGE1/regrade_v2.py --run a2_agent_gpt-5.6-terra --items STAGE1/output/a2_items.jsonl --repeat 3
# 4) C형·D형 (답만 받고 코드로 채점)
for T in c d; do
  python3 STAGE1/eval_a.py --target llm --items STAGE1/output/${T}_items.jsonl --run ${T}_llm_gpt-5.6-terra
  python3 STAGE1/eval_a.py --target agent --agent-url $AGENT --agent-reply-key answer --items STAGE1/output/${T}_items.jsonl --run ${T}_agent_gpt-5.6-terra --workers 1
  python3 STAGE1/score_cases.py --run ${T}_llm_gpt-5.6-terra --items STAGE1/output/${T}_items.jsonl
  python3 STAGE1/score_cases.py --run ${T}_agent_gpt-5.6-terra --items STAGE1/output/${T}_items.jsonl
done
```

## 실행 후 (API 없음)
```bash
# 채점자 검증표: 채점자 판정을 숨기고 임상의가 직접 채점 → κ (A·A2형)
python3 STAGE1/make_judge_check.py build --runs llm_gpt-5.6-terra agent_gpt-5.6-terra a2_llm_gpt-5.6-terra a2_agent_gpt-5.6-terra \
  --items STAGE1/output/a_items.jsonl STAGE1/output/a2_items.jsonl --out STAGE1/output/채점자검증표.xlsx --key STAGE1/output/채점자검증_key.json
# 임상의 작성 후
python3 STAGE1/make_judge_check.py score STAGE1/output/채점자검증_key.json 임상의1.xlsx 임상의2.xlsx
```
- 표본: 채점자 3회 판정이 갈린 답 전부 + 다수결 '부분' 전부 + 나머지 기준별 20%. key 파일(채점자 판정)은 임상의에게 주지 않는다.
- 예전 `human_check.csv`는 v1 채점자 기준이라 쓰지 않는다.

## 안전장치
- `eval_a.py`의 기본 단계는 `baseline`(답만 받기)이다. 예전 v1 채점자는 `--phase judge`를 명시해야만 돈다. C·D형은 v1 채점자를 거부한다.
- 답에는 받은 시점의 질문(`질문`)이 저장된다. `regrade_v2.py`와 `score_cases.py`는 지금 질문과 다른 질문의 답을 채점하지 않는다.
- 먼저 `--limit 2`로 형식을 확인하고(호출 몇 번), 이상 없으면 전체를 돌린다. 에이전트는 `--agent-ping`으로 요청 모양을 먼저 본다.
- A2형 채점은 A형과 같은 v2.1 프롬프트에 'A2형 열쇠 읽는 법'(필수 요소·이전 약제 채점·비고) 3줄만 덧붙인다(채점 버전 v2.1+A2). A형 채점 프롬프트는 바뀌지 않았다.
- C·D형 답 형식: 기본 AI는 `eval_a.py`의 `CASE_FORMAT`, 에이전트는 백엔드 `answer_style`(case·drugs)로 같은 문장을 쓴다. A·A2형은 예전과 같은 단답 형식.
