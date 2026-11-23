#!/usr/bin/env bash
# run_chain.sh가 끝나면 opus 조건을 이어서 돌린다 (Anthropic 배치 결과 받기 → 학생 로컬 재답 → …).
cd "$(dirname "$0")"
L=logs/chain.log
say() { echo "$(date '+%F %T') $*" >> $L; }
while kill -0 1122465 2>/dev/null; do sleep 15; done
for i in $(seq 1 40); do m=$(nvidia-smi --id=1 --query-gpu=memory.used --format=csv,noheader,nounits); [ "$m" -lt 3000 ] && break; sleep 15; done
say "opus 조건 시작 (opus 선생 1회차 배치는 이미 제출됨, 승인됨)"
STUDENT=qwen ARMS=opus GPU=1 ./run_qwen_loop.bash >> logs/qwen_loop_opus.log 2>&1
say "opus 조건 종료 (코드 $?)"
