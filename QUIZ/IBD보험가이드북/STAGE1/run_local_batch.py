#!/usr/bin/env python3
"""선생–학생 루프의 '로컬 배치'를 Qwen으로 채운다 (2026-11-23).

teacher_loop.py --student qwen 은 회차마다 batches/<이름>/requests.jsonl 을 만들고(next),
'로컬 실행'으로 표시한다(submit). 이 스크립트가 그 요청을 로컬 모델로 돌려 results_local.jsonl 을 쓰면,
teacher_loop.py fetch 가 OpenAI·Anthropic 배치 결과와 같은 방식으로 받아 상태에 반영한다.

모델·샘플링은 기존 Qwen 실행(eval_local_cuda.py / eval_local_mlx.py)과 같다.
  - vllm (GPU 서버, 기본): Qwen/Qwen3-14B bf16
  - mlx  (Mac, 확인용):    mlx-community/Qwen3-14B-4bit
  - 생각 모드 켬: temp 0.6 · top_p 0.95 · top_k 20. 답에서는 <think>…</think>를 뗀다 (원문도 저장).
  - 선생 요청: 스키마를 지시문에 붙여 받는다. JSON을 꺼내는 일은 teacher_loop.py fetch가 한다(못 꺼내면 '선생 오류'로 셈).
  - 이미 받은 custom_id는 건너뛴다(중간에 멈춰도 이어서).

사용 (STAGE1에서)
  .venv_cuda/bin/python run_local_batch.py --dir eval_out/teacher_loop_qwen3-14b-bf16/self-g/batches/01_teacher_r1
  .venv_cuda/bin/python run_local_batch.py --watch            # 모델을 한 번 올리고, 로컬 표시된 배치를 계속 찾아 채움 (Ctrl+C로 끝)
  .venv_mlx/bin/python  run_local_batch.py --engine mlx --dir … --limit 2   # Mac에서 두 요청만 확인
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOTS = sorted((HERE / "eval_out").glob("teacher_loop_*"))
MODELS = {"vllm": "Qwen/Qwen3-14B", "mlx": "mlx-community/Qwen3-14B-4bit"}


def strip_think(text: str) -> str:
    """eval_local_mlx.strip_think와 같음: 마지막 '</think>' 뒤만 답."""
    import re
    return (text.rsplit("</think>", 1)[-1] if "</think>" in text else re.sub(r"<think>.*?</think>", "", text, flags=re.S)).strip()


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def pending_dirs() -> list[Path]:
    """teacher_loop_<라벨>/<조건>/meta.json 의 pending이 '로컬 실행'이고 결과가 덜 찬 배치 폴더."""
    out = []
    for root in ROOTS:
        for meta in root.glob("*/meta.json"):
            p = json.loads(meta.read_text(encoding="utf-8")).get("pending") or {}
            if p.get("provider") == "local" and p.get("batch_id") == "local":
                bd = meta.parent / "batches" / p["name"]
                if len(jl(bd / "results_local.jsonl")) < p["requests"]:
                    out.append(bd)
    return out


class Engine:
    def __init__(self, a):
        self.a = a
        self.model = a.model or MODELS[a.engine]
        t0 = time.time()
        if a.engine == "vllm":
            from vllm import LLM, SamplingParams
            self.llm = LLM(model=self.model, dtype="bfloat16", gpu_memory_utilization=a.gpu_util,
                           max_model_len=a.max_model_len, seed=a.seed, enable_prefix_caching=True)
            self.tok = self.llm.get_tokenizer()
            self.sp = SamplingParams(temperature=0.6, top_p=0.95, top_k=20, max_tokens=a.max_tokens, seed=a.seed)
        else:
            from mlx_lm import load
            from mlx_lm.sample_utils import make_sampler
            self.mlx_model, self.tok = load(self.model)
            self.sampler = make_sampler(temp=0.6, top_p=0.95, top_k=20)
        print(f"모델 불러옴 {self.model} ({a.engine}) {time.time() - t0:.0f}초", flush=True)

    def prompt(self, req: dict) -> str:
        return self.tok.apply_chat_template(req["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=True)

    def run(self, reqs: list[dict]):
        """요청 묶음 → [(원문, 입력 토큰, 출력 토큰, 끝남, 초)]"""
        prompts = [self.prompt(r) for r in reqs]
        if self.a.engine == "vllm":
            t1 = time.time()
            outs = self.llm.generate(prompts, self.sp)
            sec = (time.time() - t1) / max(1, len(reqs))
            return [(o.outputs[0].text, len(o.prompt_token_ids), len(o.outputs[0].token_ids),
                     o.outputs[0].finish_reason == "stop", sec) for o in outs]
        import mlx.core as mx  # noqa: F401
        from mlx_lm import generate
        res = []
        for pr in prompts:
            t1 = time.time()
            text = generate(self.mlx_model, self.tok, pr, max_tokens=self.a.max_tokens, sampler=self.sampler)
            n_in, n_out = len(self.tok.encode(pr)), len(self.tok.encode(text))
            res.append((text, n_in, n_out, n_out < self.a.max_tokens, time.time() - t1))
        return res


def fill(eng: Engine, bd: Path, limit: int | None) -> int:
    reqs = jl(bd / "requests.jsonl")
    out = bd / "results_local.jsonl"
    done = {r["custom_id"] for r in jl(out)}
    todo = [r for r in reqs if r["custom_id"] not in done][: limit or None]
    print(f"{bd.relative_to(HERE)}: 요청 {len(reqs)} · 이미 {len(done)} · 이번 {len(todo)}", flush=True)
    n = 0
    for i in range(0, len(todo), eng.a.chunk):
        part = todo[i:i + eng.a.chunk]
        for r, (raw, n_in, n_out, fin, sec) in zip(part, eng.run(part)):
            row = {"custom_id": r["custom_id"], "kind": r["kind"], "text": strip_think(raw), "raw": raw,
                   "input_tokens": n_in, "output_tokens": n_out, "finished": fin, "초": round(sec, 1),
                   "model": eng.model, "engine": eng.a.engine, "시각": datetime.now().isoformat(timespec="seconds")}
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
        print(f"  {len(done) + n}/{len(reqs)}", flush=True)
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="선생–학생 루프 로컬 배치를 Qwen으로 채우기")
    p.add_argument("--dir", nargs="*", default=[], help="배치 폴더 (없으면 로컬 표시된 배치를 모두 찾음)")
    p.add_argument("--watch", action="store_true", help="모델을 올려 둔 채 새 로컬 배치를 계속 찾아 채움")
    p.add_argument("--engine", choices=["vllm", "mlx"], default="vllm")
    p.add_argument("--model", help="기본: vllm Qwen/Qwen3-14B, mlx mlx-community/Qwen3-14B-4bit")
    p.add_argument("--limit", type=int, help="배치마다 앞에서 N개만 (확인용)")
    p.add_argument("--chunk", type=int, default=32, help="한 번에 엔진에 넣고 저장하는 요청 수")
    p.add_argument("--max-tokens", type=int, default=6000)
    p.add_argument("--max-model-len", type=int, default=24576, help="vllm: 선생 2회차는 발췌가 길어 eval_local_cuda(16384)보다 크게")
    p.add_argument("--gpu-util", type=float, default=0.6)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    eng = Engine(a)
    while True:
        dirs = [Path(x) if Path(x).is_absolute() else HERE / x for x in a.dir] or pending_dirs()
        for bd in dirs:
            fill(eng, bd, a.limit)
        if not a.watch:
            return 0
        if not dirs:
            time.sleep(30)


if __name__ == "__main__":
    sys.exit(main())
