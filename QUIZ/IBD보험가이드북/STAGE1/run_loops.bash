#!/usr/bin/env bash
# review loop·대조 조건을 끝까지 자동으로 돌린다 (run_qwen_loop.bash를 일반화, 2026-11-24).
# init → (next → submit → fetch)를 '할 일 없음'까지 → finalize → report. 채점은 하지 않는다(GPU_SERVER_RUN_PLAN.md 참고).
#
# 환경 변수
#   STUDENT   gpt(기본) | qwen | opus        answerer 모델 (코드 이름은 student)
#   ARMS      "opus self qwen gpt route reask" 중 공백으로 여러 개   reviewer 조건 (코드 이름은 arm)
#   SOURCE    pdf(기본) | csv                발췌 출처
#   ADD_TYPES 예: "A A2 C"                    이미 있는 폴더에 이 유형만 더함 (CSV 루프처럼 D형만 끝난 폴더)
#   GPU       vLLM(로컬 Qwen)이 쓸 GPU 번호 (기본 1). Qwen이 answerer나 reviewer일 때만 vLLM을 띄운다.
#   RAG_RERANK_DEVICE  쪽 찾기 검색의 재랭커 장치 (auto·cuda:0·cpu). vLLM과 다른 GPU를 주거나, GPU가 하나면 cpu.
# 예
#   STUDENT=qwen ARMS=opus GPU=1 RAG_RERANK_DEVICE=cuda:0 nohup ./run_loops.bash > logs/loop_qwen_opus.log 2>&1 &
#   STUDENT=gpt SOURCE=csv ARMS="opus self" ADD_TYPES="A A2 C" nohup ./run_loops.bash > logs/loop_csv.log 2>&1 &
# 주의: submit --yes 로 배치를 자동 제출한다(과금). 돌리기로 정한 조건만 ARMS에 넣는다.
set -u
cd "$(dirname "$0")"
mkdir -p logs
PY=.venv_rag/bin/python
GPU=${GPU:-1}
STUDENT=${STUDENT:-gpt}
SOURCE=${SOURCE:-pdf}
ADD_TYPES=${ADD_TYPES:-}
read -ra ARMS <<< "${ARMS:?ARMS를 지정하세요 (예: ARMS=opus)}"
export RAG_RERANK_DEVICE=${RAG_RERANK_DEVICE:-auto}
T() { $PY teacher_loop.py "$@" --student "$STUDENT" --source "$SOURCE" 2>&1 | grep -vE "Warning|W1123|Loading|NOTE"; }
case "$STUDENT" in
  gpt)  LOOPDIR=eval_out/teacher_loop ;;
  qwen) LOOPDIR=eval_out/teacher_loop_qwen3-14b-bf16 ;;
  opus) LOOPDIR=eval_out/teacher_loop_claude-opus-5-5 ;;
  *) echo "STUDENT는 gpt·qwen·opus 중 하나"; exit 1 ;;
esac
SUF=""; [ "$SOURCE" = csv ] && SUF="-csv"
say() { echo "[$(date '+%F %T')] $*"; }

# 로컬 Qwen이 필요하면(answerer가 qwen이거나 reviewer에 qwen이 있으면) vLLM 러너를 띄운다
NEED_LOCAL=0
[ "$STUDENT" = qwen ] && NEED_LOCAL=1
for arm in "${ARMS[@]}"; do [ "$arm" = qwen ] && NEED_LOCAL=1; done
RUNNER=""
if [ "$NEED_LOCAL" = 1 ]; then
  CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=$GPU VLLM_USE_FLASHINFER_SAMPLER=0 \
    .venv_cuda/bin/python -u run_local_batch.py --watch >> logs/qwen_local.log 2>&1 &
  RUNNER=$!
  trap "kill $RUNNER 2>/dev/null" EXIT
  say "vLLM 러너 시작 (GPU $GPU, pid $RUNNER, 로그 logs/qwen_local.log)"
fi
say "STUDENT=$STUDENT SOURCE=$SOURCE ARMS=${ARMS[*]} ADD_TYPES=${ADD_TYPES:-없음} RAG_RERANK_DEVICE=$RAG_RERANK_DEVICE"

declare -A done
for arm in "${ARMS[@]}"; do
  if [ "$arm" = route ] || [ "$arm" = reask ]; then sub=$arm$SUF; else sub=$arm-g$SUF; fi
  if [ ! -f "$LOOPDIR/$sub/state.jsonl" ]; then
    say "$arm init"; T init --arm "$arm"
  elif [ -n "$ADD_TYPES" ]; then
    say "$arm init --add --types $ADD_TYPES"; T init --arm "$arm" --add --types $ADD_TYPES || true
  fi
  done[$arm]=0
done

while true; do
  left=0
  for arm in "${ARMS[@]}"; do
    [ "${done[$arm]}" = 1 ] && continue
    left=1
    out=$(T fetch --arm "$arm")
    if echo "$out" | grep -q "아직 끝나지"; then continue; fi
    say "$arm fetch: $out"
    n=$(T next --arm "$arm"); say "$arm next: $n"
    if echo "$n" | grep -q "할 일 없음"; then
      T finalize --arm "$arm"; T report --arm "$arm" > /dev/null; done[$arm]=1
      say "$arm 끝 (finalize·report 완료)"; continue
    fi
    T submit --arm "$arm" --yes
  done
  [ "$left" = 0 ] && break
  if [ -n "$RUNNER" ]; then kill -0 "$RUNNER" 2>/dev/null || { say "run_local_batch.py가 멈춤 (logs/qwen_local.log)"; exit 1; }; fi
  sleep 60
done
say "루프 끝. 다음: 채점 (GPU_SERVER_RUN_PLAN.md 5단계)"
