# GPU 서버 실행 계획 (2026-11-24)

380문항(A 101+보조 6, A2 38, C 198, D 37)만 쓴다. 확장 문항(c_ext, d_ext)은 돌리지 않는다.
용어: 덱의 **reviewer = 코드의 선생(teacher, `--arm`)**, **answerer = 코드의 학생(student, `--student`)**.

## 0. 규칙

- **과금되는 단계는 이 문서에서 고른 번호만 돌린다.** 각 단계의 `next`가 찍는 예상 비용이 아래 표의 범위를 크게 넘으면 제출하지 말고 멈춘 뒤 보고한다.
- 모든 API 호출은 배치(50% 할인)로 보낸다. `run_loops.bash`는 `submit --yes`로 자동 제출하므로, 돌리기로 정한 조건만 `ARMS`에 넣는다.
- 한 단계가 끝나면 `report`와 채점 결과를 확인하고 다음 단계로 넘어간다.

## 1. 준비 (무료)

```bash
cd <저장소>/QUIZ/IBD보험가이드북/STAGE1
git fetch origin && git checkout stage1-gpu-run-prep && git pull   # 2026-11-24 코드 변경이 있는 브랜치 (아래 '바뀐 코드')
nvidia-smi                                 # GPU 번호·여유 메모리 확인
.venv_cuda/bin/python -c "import vllm; print(vllm.__version__)"
.venv_rag/bin/python -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.device_count())"
.venv_rag/bin/python -c "import sys; sys.path.insert(0,'../../../backend'); from app.rag.rerank import rerank_device; print(rerank_device())"
grep -l OPENAI_API_KEY ../.env .env ../../../data/RAG/.env 2>/dev/null       # OpenAI 키 위치 (값은 출력하지 않음)
grep -l ANTHROPIC_API_KEY ../.env .env 2>/dev/null                            # Anthropic 키 위치
```

- `.venv_rag`의 torch가 `cuda False`이면 재랭커는 CPU로 돈다(느리지만 결과는 같음). GPU로 돌리려면 `.venv_rag`에 CUDA판 torch를 깐다.
- GPU 배정: vLLM(Qwen)은 `GPU=1`(기본), 재랭커는 다른 GPU `RAG_RERANK_DEVICE=cuda:0`. GPU가 하나뿐이면 `RAG_RERANK_DEVICE=cpu`로 둔다(vLLM이 메모리를 거의 다 잡기 때문).
- 재랭커는 review loop에서 reviewer가 '검색'으로 쪽을 찾을 때만 쓴다. GPU·CPU 결과는 같다(2026-11-24 Mac에서 MPS·CPU 순위·점수 동일 확인, float32 그대로).

### 바뀐 코드 (2026-11-24)
- `backend/app/rag/rerank.py`: 재랭커 장치를 `RAG_RERANK_DEVICE`로 고름 (auto = CUDA → MPS → CPU)
- `teacher_loop.py`: `--student opus`(Opus answerer), `--arm gpt`(gpt reviewer + 다른 answerer), `init --add --types`(끝난 폴더에 유형 추가)
- `eval_claude_batch.py`: `--arms llm-same`(Opus 같은 틀 기본 AI)
- `run_loops.bash`: 새 자동 실행 스크립트 (answerer·reviewer·출처를 환경 변수로)

## 2. 실행 순서

| 순서 | # | 실험 | 명령 (STAGE1에서) | API 비용 (배치, 추정) | GPU |
|---|---|---|---|---|---|
| 1 | 1 | Opus reviewer + Qwen answerer 마무리 | `STUDENT=qwen ARMS=opus GPU=1 RAG_RERANK_DEVICE=cuda:0 nohup ./run_loops.bash > logs/loop_qwen_opus.log 2>&1 &` | Anthropic $3~4 (reviewer 2회차 153건, 이미 만든 배치) | vLLM |
| 2 | 2 | Qwen answerer + gpt reviewer | `STUDENT=qwen ARMS=gpt GPU=1 RAG_RERANK_DEVICE=cuda:0 nohup ./run_loops.bash > logs/loop_qwen_gpt.log 2>&1 &` | OpenAI 1회차 $2.7~5 + 2회차 | vLLM |
| 3 | 6c | CSV loop, Qwen reviewer (gpt answerer, 4유형) | `STUDENT=gpt SOURCE=csv ARMS=qwen GPU=1 RAG_RERANK_DEVICE=cuda:0 nohup ./run_loops.bash > logs/loop_csv_qwen.log 2>&1 &` | OpenAI answerer 몇 달러 | vLLM |
| 4 | 6a·6b | CSV loop A·A2·C 추가, Opus·gpt reviewer | `STUDENT=gpt SOURCE=csv ARMS="opus self" ADD_TYPES="A A2 C" RAG_RERANK_DEVICE=cuda:0 nohup ./run_loops.bash > logs/loop_csv_add.log 2>&1 &` | Anthropic 1회차 $10.6~14 + OpenAI 1회차 $4.1~6.2, 각각 2회차 추가 | 재랭커만 |
| 5 | 7 | CSV-RAG 다시 (대조군) | `STUDENT=gpt SOURCE=csv ARMS=reask nohup ./run_loops.bash > logs/loop_csv_reask.log 2>&1 &` | OpenAI $3.7~7.5 | 없음 |
| 6 | 4·5 | Opus answerer: 규칙으로 쪽 추가 · 기본 RAG 다시 | `STUDENT=opus ARMS="route reask" nohup ./run_loops.bash > logs/loop_opus.log 2>&1 &` | Anthropic $6~12 + $4~11 | 없음 |
| 7 | 3 | Opus 같은 틀 기본 AI | 아래 3절 | Anthropic $4~12 | 없음 |

- 1~3은 같은 vLLM GPU를 쓰므로 **차례로** 돌린다(한 번에 하나). 4~7은 GPU가 필요 없어 1~3과 동시에 돌려도 된다.
- 순서 4는 `opus-g-csv`, `self-g-csv` 폴더에 이미 있는 D형 37문항을 그대로 두고 A·A2·C 343문항만 새로 돈다.
- loop 2회차 비용은 1회차 결과에 따라 정해진다(지금까지 1회차의 20~30%).

## 3. Opus 같은 틀 기본 AI (loop 아님)

```bash
.venv_claude/bin/python eval_claude_batch.py build  --tag same-opus --arms llm-same      # 요청 380개·예상 비용 출력 (무료)
.venv_claude/bin/python eval_claude_batch.py submit --tag same-opus --yes                # 과금
.venv_claude/bin/python eval_claude_batch.py status --tag same-opus                      # 끝날 때까지 가끔 확인
.venv_claude/bin/python eval_claude_batch.py fetch  --tag same-opus                      # → eval_out/{,a2_,c_,d_}llm-same_claude-opus-5-5/
```

## 4. 진행 확인

```bash
tail -n 20 logs/loop_*.log          # 단계별 fetch/next/submit 기록
tail -n 5 logs/qwen_local.log       # vLLM 러너 진행
.venv_rag/bin/python teacher_loop.py status --arm <arm> --student <student> [--source csv]
```

멈췄을 때: `run_local_batch.py가 멈춤`이면 `logs/qwen_local.log`의 마지막 오류를 본다. 다시 돌리면 이어서 한다(받은 결과는 건너뜀).

## 5. 채점

C·D형은 코드 채점(무료), A·A2형은 gpt-6-sol 배치(OpenAI, 조건마다 약 $1).

| 실험 | 결과 폴더 이름 (`<p>` = 없음·a2_·c_·d_) |
|---|---|
| 1 | `<p>loop-opus-g_qwen3-14b-bf16` |
| 2 | `<p>loop-gpt-g_qwen3-14b-bf16` |
| 3 | `<p>loop-qwen-g-csv_gpt-5.6-terra` |
| 4 | `<p>loop-opus-g-csv_gpt-5.6-terra`, `<p>loop-self-g-csv_gpt-5.6-terra` |
| 5 | `<p>loop-reask-csv_gpt-5.6-terra` |
| 6 | `<p>loop-route_claude-opus-5-5`, `<p>loop-reask_claude-opus-5-5` |
| 7 | `<p>llm-same_claude-opus-5-5` |

```bash
# C·D형 (무료). RUN에 위 이름(접두어 없이)을 넣는다
for RUN in loop-opus-g_qwen3-14b-bf16 ; do
  python3 score_cases.py --run c_$RUN --items output/c_items.jsonl
  python3 score_cases.py --run d_$RUN --items output/d_items.jsonl
done
# A·A2형 (과금). 여러 실험을 한 배치로 묶는다
.venv_claude/bin/python regrade_v2_batch.py build --job loop-opus-g_qwen3-14b-bf16:output/a_items.jsonl --job a2_loop-opus-g_qwen3-14b-bf16:output/a2_items.jsonl  # … 실험마다 --job 두 개
.venv_claude/bin/python regrade_v2_batch.py submit --tag <build가 알려 준 tag> --yes
.venv_claude/bin/python regrade_v2_batch.py fetch  --tag <tag>
```

## 6. 끝나면

- `eval_out/` 변경(상태·배치·답·채점·usage.json)을 커밋하고 푸시한다. 이전 Qwen 실행 결과를 돌려보낸 방식과 같다.
- 실험마다 보고: 끝난 회차, `report`의 판정 분포·누설 의심, 유형별 점수, 실제 비용(`usage.json`).

## 비용 요약 (1~7 전부)

| 키 | 추정 |
|---|---|
| Anthropic | 약 $30~55 |
| OpenAI | 약 $25~35 (A·A2 채점 포함) |
| 로컬 GPU | Qwen 작업 1~3 |
