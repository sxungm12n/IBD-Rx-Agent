# 판정 주체 구분 (2026-11-10)

- `graded.jsonl` : LLM 채점자 v1 (gpt-6-sol)
- `graded_v2*.jsonl` : LLM 채점자 v2 (원문 쪽·척도 범위 제공)
- `graded_v21*.jsonl` : LLM 채점자 v2.1 (+ 연구자가 확정한 채점 규칙 1~3). **논문 주 결과용**. `_r1`, `_r2`는 반복 채점, 다수결 사용.
- `claude_review_NOT_human.csv` : 예전 이름 `human_overrides.csv`. **Claude가 검토한 판정이며 사람 판정이 아님.**
  논문의 기준 정답으로 쓰지 않는다. 임상의 검증 채점 목록에 넣어 다시 판정받는다.
  (eval_a.py는 `human_overrides.csv`만 읽으므로, 이름을 바꾼 뒤로는 자동 반영되지 않는다.)
- 실제 사람 판정은 임상의 검증 채점이 끝나면 `human_overrides.csv`로 새로 만든다 (보정자 칸에 임상의 이름).
