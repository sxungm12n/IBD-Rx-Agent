#!/usr/bin/env python3
"""2026-11-12 문항 수정 이전(2026-11-10) A형 채점 상태를 따로 폴더에 다시 만든다. API 없음.

11-12에 질문이 바뀐 24문항·채점 열쇠만 바뀐 7문항은 새로 답을 받거나 다시 채점했고,
그 전의 답·채점은 eval_out/<run>/superseded_*.jsonl 로 옮겨 두었다. 이 스크립트는
'지금 파일 + superseded 파일(옛 판정이 우선)'과 output/_backup_20261110/a_items.jsonl 로
11-10 상태를 만든다. 원래 폴더는 건드리지 않는다.

사용 (IBD보험가이드북 폴더에서):
  python3 STAGE1/_archive/scripts/rebuild_20261110_state.py STAGE1 /tmp/stage1_20261110
  python3 STAGE1/_archive/scripts/compare_v2.py /tmp/stage1_20261110 v21   # = eval_out/regrade_v21_compare.txt
  python3 STAGE1/_archive/scripts/compare_v2.py /tmp/stage1_20261110 v2    # = eval_out/regrade_v2_compare.txt (숫자 같음, 표기만 '교정'→'Claude 검토')
2026-11-15 확인: v21은 글자 하나까지 같고, v2는 숫자가 모두 같다.
"""
import json
import shutil
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
if dst.exists():
    sys.exit(f"{dst} 가 이미 있습니다. 빈 경로를 주세요.")
(dst / "output").mkdir(parents=True)
shutil.copy(src / "output" / "_backup_20261110" / "a_items.jsonl", dst / "output" / "a_items.jsonl")
for run in ["llm_gpt-5.6-terra", "agent_gpt-5.6-terra"]:
    s, d = src / "eval_out" / run, dst / "eval_out" / run
    d.mkdir(parents=True)
    shutil.copy(s / "claude_review_NOT_human.csv", d)
    for name in ["graded", "graded_v2", "graded_v2_r1", "graded_v2_r2", "graded_v21", "graded_v21_r1", "graded_v21_r2"]:
        rows = {}
        for f in [s / f"{name}.jsonl", s / f"superseded_{name}.jsonl"]:  # 뒤의 옛 판정이 지금 판정을 덮어씀
            if f.exists():
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        rows[json.loads(line)["id"]] = line
        (d / f"{name}.jsonl").write_text("".join(v + "\n" for v in rows.values()), encoding="utf-8")
print(f"11-10 상태 → {dst}")
