#!/usr/bin/env bash
# 루프 진행 상황을 logs/STATUS_loop.txt(한 줄, 덮어씀)와 logs/loop_progress.log(이어 붙임)에 1분마다 남긴다.
cd "$(dirname "$0")"; mkdir -p logs
while true; do
  line="$(date '+%F %T') | 로컬 배치: $(grep -E '^  [0-9]+/[0-9]+' logs/qwen_local.log | tail -1 | tr -d ' ') | 루프: $(grep -E '^\[[0-9:]+\]' logs/qwen_loop.log logs/qwen_loop_gpt.log 2>/dev/null | tail -1 | cut -d: -f2- | cut -c1-110) | 실행 프로세스 $(pgrep -u "$USER" -f 'run_qwen_loop|run_local_batch' | wc -l)개"
  echo "$line" > logs/STATUS_loop.txt
  echo "$line" >> logs/loop_progress.log
  sleep 60
done
