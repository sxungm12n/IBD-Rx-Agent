#!/usr/bin/env bash
# run_qwen_loop.sh(zsh)의 bash 판. zsh가 없는 서버용이고 동작은 같다 (zsh 배열 문법만 bash로 바꿈).
# 사용: STUDENT=qwen ARMS=reask GPU=1 nohup ./run_qwen_loop.bash > logs/qwen_loop.log 2>&1 &
#   STUDENT=qwen(기본) : 학생 Qwen3-14B, 조건 reask route self opus
#   STUDENT=gpt        : 학생 gpt-5.6-terra, 조건 qwen (선생 = 로컬 Qwen)
set -u
cd "$(dirname "$0")"
mkdir -p logs
PY=.venv_rag/bin/python
GPU=${GPU:-1}
STUDENT=${STUDENT:-qwen}
read -ra ARMS <<< "${ARMS:-reask route self opus}"
T() { $PY teacher_loop.py "$@" --student "$STUDENT" 2>&1 | grep -vE "Warning|W1123|Loading|NOTE"; }
if [ "$STUDENT" = qwen ]; then LOOPDIR=eval_out/teacher_loop_qwen3-14b-bf16; else LOOPDIR=eval_out/teacher_loop; fi

CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU VLLM_USE_FLASHINFER_SAMPLER=0 \
  .venv_cuda/bin/python -u run_local_batch.py --watch >> logs/qwen_local.log 2>&1 &
RUNNER=$!
trap "kill $RUNNER 2>/dev/null" EXIT

declare -A done
for arm in "${ARMS[@]}"; do
  if [ "$arm" = route ] || [ "$arm" = reask ]; then sub=$arm; else sub=$arm-g; fi
  [ -f "$LOOPDIR/$sub/state.jsonl" ] || T init --arm "$arm"
  done[$arm]=0
done
while true; do
  left=0
  for arm in "${ARMS[@]}"; do
    [ "${done[$arm]}" = 1 ] && continue
    left=1
    out=$(T fetch --arm "$arm")
    if echo "$out" | grep -q "아직 끝나지"; then continue; fi
    echo "[$(date +%T)] $arm fetch: $out"
    n=$(T next --arm "$arm"); echo "[$(date +%T)] $arm next: $n"
    if echo "$n" | grep -q "할 일 없음"; then
      T finalize --arm "$arm"; T report --arm "$arm" > /dev/null; done[$arm]=1; continue
    fi
    T submit --arm "$arm" --yes
  done
  [ "$left" = 0 ] && break
  kill -0 $RUNNER 2>/dev/null || { echo "run_local_batch.py가 멈춤 (logs/qwen_local.log)"; exit 1; }
  sleep 60
done
echo "[$(date +%T)] 루프 끝."
