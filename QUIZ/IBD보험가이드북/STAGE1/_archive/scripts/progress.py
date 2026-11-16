#!/usr/bin/env python3
"""지금 실행 중인 평가의 진행 상황 (API 없음). 사용: python3 STAGE1/progress.py"""
import datetime as dt
import json
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "eval_out"
RUNS = {  # 결과 폴더: 이번에 받을 문항 수
    "llm_gpt-5.6-terra": 24, "a2_llm_gpt-5.6-terra": 38, "c_llm_gpt-5.6-terra": 198, "d_llm_gpt-5.6-terra": 37,
    "agent_gpt-5.6-terra": 24, "a2_agent_gpt-5.6-terra": 38, "c_agent_gpt-5.6-terra": 198, "d_agent_gpt-5.6-terra": 37,
}

running = subprocess.run(["pgrep", "-f", "run_agent.sh|run_llm.sh|eval_a.py|regrade_v2.py"], capture_output=True).stdout.strip()
print("실행 중인 평가 프로세스:", "있음" if running else "없음")
for side in ("llm", "agent"):
    done = total = 0
    secs, last = [], ""
    print(f"\n[{'기본 AI' if side == 'llm' else '에이전트'}]")
    for run, n in RUNS.items():
        if not run.replace("a2_", "").replace("c_", "").replace("d_", "").startswith(side):
            continue
        path = OUT / run / "answers.jsonl"
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
        new = [r for r in rows if r.get("질문")]  # 이번 문항 버전으로 받은 답
        done, total = done + len(new), total + n
        secs += [r.get("초", 0) for r in new]
        last = max([last] + [r.get("시각", "") for r in new])
        print(f"  {run:<26} {len(new):>3} / {n}")
    avg = sum(secs) / len(secs) if secs else 0
    left = (total - done) * avg / 60
    print(f"  합계 {done} / {total}, 평균 {avg:.0f}초, 마지막 답 {last[11:19] or '-'}"
          + (f", 남은 예상 약 {left:.0f}분" if done < total and avg else ""))
print("\n지금 시각", dt.datetime.now().strftime("%H:%M:%S"))
