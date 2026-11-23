#!/usr/bin/env bash
# 1단계(reask)가 끝나면 이어서 route·self, 그다음 gpt 학생 + Qwen 선생을 돌린다. opus 선생(과금)은 승인 후 따로 돌린다.
# 로그: logs/chain.log
cd "$(dirname "$0")"
L=logs/chain.log
say() { echo "$(date '+%F %T') $*" >> $L; }
FIRST_PID=$1
say "대기: 1단계 프로세스 $FIRST_PID 종료"
while kill -0 "$FIRST_PID" 2>/dev/null; do sleep 15; done
gpu_free() { for i in $(seq 1 40); do m=$(nvidia-smi --id=1 --query-gpu=memory.used --format=csv,noheader,nounits); [ "$m" -lt 3000 ] && return 0; sleep 15; done; return 1; }
gpu_free || { say "GPU 1이 안 비워짐 - 중단"; exit 1; }
say "1단계 끝. route + self 시작 (GPU 1)"
STUDENT=qwen ARMS="route self" GPU=1 ./run_qwen_loop.bash >> logs/qwen_loop_route_self.log 2>&1
say "route + self 종료 (코드 $?)"
gpu_free || { say "GPU 1이 안 비워짐 - 중단"; exit 1; }
say "4단계: gpt 학생 + Qwen 선생 시작 (gpt 재답 과금 약 \$1, 사용자가 사전 승인)"
STUDENT=gpt ARMS=qwen GPU=1 ./run_qwen_loop.bash >> logs/qwen_loop_gpt.log 2>&1
say "4단계 종료 (코드 $?)"
