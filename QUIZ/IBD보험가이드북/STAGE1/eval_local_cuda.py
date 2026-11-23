#!/usr/bin/env python3
"""NVIDIA GPU(CUDA)에서 Qwen3-14B로 답 받기 (vLLM, API 요금 없음).

eval_local_mlx.py의 CUDA 판이다. 문항·지시문·발췌·샘플링·저장 모양은 MLX 판과 같다
(plan·save·strip_think를 그대로 import해서 쓴다). 바뀌는 것은 실행 엔진(MLX → vLLM)과
모델 가중치(mlx 4bit → 원본 Qwen/Qwen3-14B bf16)뿐이다.

  - 기본 모델: Qwen/Qwen3-14B (bf16, 약 30GB). 결과 라벨은 qwen3-14b-bf16
    (MLX 4bit 결과 qwen3-14b-4bit 와 섞이지 않게 폴더 이름이 다르다).
  - GPU: 기본 1번 하나. 공유 서버라 CUDA_VISIBLE_DEVICES를 이 스크립트가 고정한다(--gpu로 변경).
  - 생각 모드·샘플링: MLX 판과 같다. 켬 temp 0.6·top_p 0.95·top_k 20, 끔 temp 0.7·top_p 0.8·top_k 20.
  - 이미 받은 답은 건너뛴다(중간에 멈춰도 이어서 실행). --chunk 문항마다 저장한다.

사용 (STAGE1 폴더에서)
  .venv_cuda/bin/python eval_local_cuda.py --types C D --limit 5 --think on     # 파일럿
  .venv_cuda/bin/python eval_local_cuda.py --limit 1 --types C --arms agent      # 속도 확인
결과: eval_out/{,a2_,c_,d_}{llm,agent}_qwen3-14b-bf16/answers.jsonl, 실행 기록 eval_out/local_cuda/<라벨>_runs.jsonl
채점: C·D형 python3 score_cases.py --run c_agent_qwen3-14b-bf16 --items output/c_items.jsonl (무료)
"""
import argparse
import os
import sys
import time

# GPU 고정은 torch/vllm을 import하기 전에 해야 한다.
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--gpu", default="1")
_gpu = _pre.parse_known_args()[0].gpu
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"  # nvidia-smi 번호와 같은 순서
os.environ["CUDA_VISIBLE_DEVICES"] = _gpu

import eval_local_mlx as M  # noqa: E402  (plan·save·strip_think 재사용)
B = M.B


def main() -> int:
    p = argparse.ArgumentParser(description="CUDA(vLLM)로 Qwen3-14B 답 받기")
    p.add_argument("--gpu", default="1", help="사용할 GPU 번호(nvidia-smi·nvtop 기준). 기본 1")
    p.add_argument("--model", default="Qwen/Qwen3-14B")
    p.add_argument("--label", default="qwen3-14b-bf16", help="결과 폴더 이름에 붙는 모델 라벨")
    p.add_argument("--types", nargs="+", default=list(B.TYPES), choices=list(B.TYPES))
    p.add_argument("--arms", nargs="+", default=["llm", "agent"], choices=["llm", "agent", "llm-same"])
    p.add_argument("--limit", type=int, help="유형마다 앞에서 N문항만")
    p.add_argument("--think", choices=["on", "off"], default="on")
    p.add_argument("--max-tokens", type=int, default=6000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--chunk", type=int, default=16, help="한 번에 vLLM에 넣고 저장하는 문항 수(vLLM이 안에서 연속 배치로 처리)")
    p.add_argument("--gpu-util", type=float, default=0.6, help="GPU 메모리 중 vLLM이 쓸 비율(공유 서버라 기본 0.6)")
    p.add_argument("--max-model-len", type=int, default=16384)
    a = p.parse_args()
    a.batch = a.chunk  # M.save가 기록하는 '배치' 값

    todo = M.plan(a, a.label)
    print(f"할 일 {len(todo)}개 · 모델 {a.model} · GPU {a.gpu} · 생각 모드 {a.think}")
    if not todo:
        return 0

    from vllm import LLM, SamplingParams

    t0 = time.time()
    llm = LLM(model=a.model, dtype="bfloat16", gpu_memory_utilization=a.gpu_util,
              max_model_len=a.max_model_len, seed=a.seed, enable_prefix_caching=True)
    print(f"모델 불러옴 {time.time() - t0:.0f}초")
    tok = llm.get_tokenizer()
    think = a.think == "on"
    sp = SamplingParams(temperature=0.6, top_p=0.95, top_k=20, max_tokens=a.max_tokens, seed=a.seed) if think else \
        SamplingParams(temperature=0.7, top_p=0.8, top_k=20, max_tokens=a.max_tokens, seed=a.seed)
    log = B.EV / "local_cuda" / f"{a.label}_runs.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)

    done, t_all = 0, time.time()
    for i in range(0, len(todo), a.chunk):
        part = todo[i:i + a.chunk]
        prompts = [tok.apply_chat_template([{"role": "system", "content": t["system"]}, {"role": "user", "content": t["user"]}],
                                           tokenize=False, add_generation_prompt=True, enable_thinking=think) for t in part]
        t1 = time.time()
        outs = llm.generate(prompts, sp)
        sec_chunk = time.time() - t1
        for t, o in zip(part, outs):
            c = o.outputs[0]
            n_out, n_in = len(c.token_ids), len(o.prompt_token_ids)
            m = o.metrics
            sec = (m.finished_time - m.first_scheduled_time) if m and getattr(m, "finished_time", None) and getattr(m, "first_scheduled_time", None) else sec_chunk
            reply = M.save(a, t, c.text, sec, n_in, n_out, c.finish_reason == "stop", None, round(n_out / sec, 1) if sec else None, log)
            done += 1
            el = time.time() - t_all
            print(f"[{done}/{len(todo)}] {t['type']} {t['arm']:5} {t['item']['id']}  {sec:5.1f}초  출력 {n_out}토큰"
                  f"  누적 {el / 60:.1f}분  {'' if c.finish_reason == 'stop' else '(길이 한도에서 끊김)'}"
                  f"  → {reply.splitlines()[0][:40] if reply else '(빈 답)'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
