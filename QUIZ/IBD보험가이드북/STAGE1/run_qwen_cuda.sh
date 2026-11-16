#!/usr/bin/env bash
# Qwen3-14B(CUDA, vLLM) 준비·실행. 터미널을 안 봐도 진행 상황을 알 수 있게 파일로 남긴다.
#
#   logs/qwen_cuda.log   전체 진행 기록 (시각 포함, 계속 이어 붙음)
#   logs/STATUS.txt      지금 어느 단계인지 한 줄 (덮어씀)
#   logs/download.log    모델 다운로드 출력
#   logs/eval.log        답 받기 실행 출력 (문항별 진행 줄)
#
# 사용 (STAGE1 폴더에서)
#   nohup ./run_qwen_cuda.sh > /dev/null 2>&1 &            # 파일럿 (C·D형 5문항, 두 대상)
#   nohup ./run_qwen_cuda.sh --types C D A A2 > /dev/null 2>&1 &   # 이후 인자는 eval_local_cuda.py로 그대로 전달
# 확인
#   cat logs/STATUS.txt ; tail -n 20 logs/qwen_cuda.log
set -u
cd "$(dirname "$0")"
mkdir -p logs
PY=.venv_cuda/bin/python
export VLLM_USE_FLASHINFER_SAMPLER=0   # nvcc/ninja 없는 서버: FlashInfer JIT 샘플러 끄고 PyTorch 샘플러 사용
LOG=logs/qwen_cuda.log
MODEL=Qwen/Qwen3-14B
GPU=${GPU:-1}                       # nvidia-smi·nvtop 번호. 바꾸려면 GPU=0 ./run_qwen_cuda.sh
ARGS=("$@"); [ ${#ARGS[@]} -eq 0 ] && ARGS=(--types C D --limit 5 --think on)

log()    { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
status() { echo "$(date '+%F %T') $*" > logs/STATUS.txt; log "[상태] $*"; }
fail()   { status "실패: $*"; exit 1; }

log "==== 시작 (GPU $GPU, 인자: ${ARGS[*]}) ===="

# 1) vLLM 확인
status "1/3 vLLM 확인 중"
$PY -c "import vllm; print('vllm', vllm.__version__)" >> "$LOG" 2>&1 || fail "vLLM import 안 됨 (logs/qwen_cuda.log 참고)"

# 2) 모델 다운로드 (이미 있으면 바로 끝남, 끊겨도 이어받기)
status "2/3 모델 다운로드 중 ($MODEL, 약 30GB)"
CACHE="${HF_HOME:-$HOME/.cache/huggingface}/hub/models--${MODEL//\//--}"
( while true; do
    echo "$(date '+%F %T') 다운로드 크기 $(du -shL "$CACHE" 2>/dev/null | cut -f1) / 약 30G, /home 여유 $(df -h /home | tail -1 | awk '{print $4}')" >> "$LOG"
    sleep 30
  done ) &
MON=$!
HF_HUB_DISABLE_PROGRESS_BARS=1 .venv_cuda/bin/hf download "$MODEL" > logs/download.log 2>&1
RC=$?
kill $MON 2>/dev/null
[ $RC -eq 0 ] || fail "다운로드 실패 (logs/download.log 참고)"
log "다운로드 완료: $(du -shL "$CACHE" 2>/dev/null | cut -f1)"

# 3) 답 받기
status "3/3 답 받기 실행 중 (진행: logs/eval.log)"
( while true; do
    DONE=$(grep -c '^\[[0-9]*/' logs/eval.log 2>/dev/null)
    TOTAL=$(grep -o '할 일 [0-9]*개' logs/eval.log 2>/dev/null | tail -1 | grep -o '[0-9]*')
    echo "$(date '+%F %T') 답 받기 진행 ${DONE:-0}/${TOTAL:-?} (이번 실행 기준), 마지막: $(grep '^\[[0-9]*/' logs/eval.log | tail -1 | cut -c1-70)" >> "$LOG"
    echo "$(date '+%F %T') 3/3 답 받기 실행 중 ${DONE:-0}/${TOTAL:-?}" > logs/STATUS.txt
    sleep 60
  done ) &
MON2=$!
CUDA_DEVICE_ORDER=PCI_BUS_ID $PY -u eval_local_cuda.py --gpu "$GPU" "${ARGS[@]}" >> logs/eval.log 2>&1
RC=$?
kill $MON2 2>/dev/null
[ $RC -eq 0 ] || fail "답 받기 실패 (logs/eval.log 마지막 줄 참고)"
status "완료 ($(grep -c '^\[[0-9]*/' logs/eval.log) 줄 진행 기록, 결과: eval_out/*_qwen3-14b-bf16/)"
log "==== 끝 ===="
