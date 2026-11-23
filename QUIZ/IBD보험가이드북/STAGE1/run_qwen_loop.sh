#!/usr/bin/env zsh
# Qwen3-14B 학생으로 선생–학생 루프 전체 실행 (2026-11-23). GPU 서버에서 STAGE1 폴더 기준.
#
# 필요한 것
#   .venv_rag   teacher_loop.py (쪽 조회·검색: 백엔드 RAG 코드, csv_rag_retrieve.py 설명의 패키지)
#   .venv_cuda  run_local_batch.py (vLLM)
#   .env        ANTHROPIC_API_KEY (opus 선생), OPENAI_API_KEY ('검색' 쪽 찾기의 질문 임베딩)
# 조건: reask · route · self(선생 = Qwen 자신, 로컬) · opus(선생 = Claude Opus, Anthropic 배치)
# 0회차 답은 기존 Qwen PDF 에이전트 답(eval_out/*agent_qwen3-14b-bf16). 같은 틀 기본 AI는 아래 마지막 줄 참고.
#
# 사용
#   nohup ./run_qwen_loop.sh > logs/qwen_loop.log 2>&1 &         # 네 조건 모두
#   ARMS="reask self" ./run_qwen_loop.sh                          # 일부만
#   tail -f logs/qwen_loop.log
# opus 선생 배치는 과금된다 (gpt 학생 기준 380문항 약 $8). 로컬 Qwen 부분은 요금 없음.
set -u
cd "$(dirname "$0")"
mkdir -p logs
PY=.venv_rag/bin/python
GPU=${GPU:-1}
ARMS=(${=ARMS:-reask route self opus})
T() { $PY teacher_loop.py "$@" --student qwen 2>&1 | grep -vE "Warning|W1123|Loading|NOTE"; }

# 로컬 배치를 채우는 vLLM 프로세스 (모델을 한 번 올려 두고 새 배치를 계속 찾음)
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU VLLM_USE_FLASHINFER_SAMPLER=0 \
  .venv_cuda/bin/python -u run_local_batch.py --watch >> logs/qwen_local.log 2>&1 &
RUNNER=$!
trap "kill $RUNNER 2>/dev/null" EXIT

typeset -A done
for arm in $ARMS; do
  [[ -f eval_out/teacher_loop_qwen3-14b-bf16/$( [[ $arm == self || $arm == opus ]] && echo $arm-g || echo $arm )/state.jsonl ]] || T init --arm $arm
  done[$arm]=0
done
while true; do
  left=0
  for arm in $ARMS; do
    [[ $done[$arm] == 1 ]] && continue
    left=1
    out=$(T fetch --arm $arm)
    if echo "$out" | grep -q "아직 끝나지"; then continue; fi
    echo "[$(date +%T)] $arm fetch: $out"
    n=$(T next --arm $arm); echo "[$(date +%T)] $arm next: $n"
    if echo "$n" | grep -q "할 일 없음"; then
      T finalize --arm $arm; T report --arm $arm > /dev/null; done[$arm]=1; continue
    fi
    T submit --arm $arm --yes
  done
  [[ $left == 0 ]] && break
  kill -0 $RUNNER 2>/dev/null || { echo "run_local_batch.py가 멈춤 (logs/qwen_local.log)"; exit 1; }
  sleep 60
done
echo "[$(date +%T)] 루프 끝. 채점: C·D score_cases.py, A·A2 regrade_v2_batch.py (…loop-<조건>_qwen3-14b-bf16)"
# 같은 틀 기본 AI (Qwen): .venv_cuda/bin/python eval_local_cuda.py --arms llm-same   (결과 eval_out/*llm-same_qwen3-14b-bf16)
