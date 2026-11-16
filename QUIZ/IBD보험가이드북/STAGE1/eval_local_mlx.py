#!/usr/bin/env python3
"""내 Mac(Apple 칩)에서 공개 모델로 답 받기 (MLX, API 요금 없음, 2026-11-16).

eval_claude_batch.py와 같은 문항·지시문·발췌로 공개 모델의 답을 받는다.
  - 지시문과 문제 문장: eval_claude_batch.llm_prompt / agent_prompt를 그대로 쓴다(= eval_a.py, backend generate.py와 같은 문자열).
  - 에이전트 발췌: gpt-5.6-terra 에이전트가 검색한 5쪽을 그대로 넣는다(검색 결과 동일).
  - 모델: 기본 mlx-community/Qwen3-14B-4bit (Hugging Face, Apache 2.0). Qwen3 채팅 틀(chat template)을 쓴다.
  - 생각 모드(--think on/off): Qwen3는 답 전에 <think>…</think>를 쓴다. 답에서는 이 부분을 떼고 저장한다.
  - 샘플링: Qwen3 권장값. 생각 모드 켬 temp 0.6·top_p 0.95·top_k 20, 끔 temp 0.7·top_p 0.8·top_k 20. 시드 고정.
  - 이미 받은 답은 건너뛴다(중간에 멈춰도 이어서 실행).

사용
  .venv_mlx/bin/python eval_local_mlx.py --types C D --limit 5 --think on     # 파일럿 (C·D 5문항씩 × 두 대상 = 20)
  .venv_mlx/bin/python eval_local_mlx.py --limit 1 --types C --arms agent      # 속도 확인 1문항
결과: eval_out/{,a2_,c_,d_}{llm,agent}_<라벨>/answers.jsonl (기존 결과와 같은 모양), 실행 기록 eval_out/local_mlx/<라벨>_runs.jsonl
채점: C·D형 python3 score_cases.py --run c_agent_<라벨> --items output/c_items.jsonl (무료)
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eval_claude_batch as B  # noqa: E402  (지시문·문항·발췌·폴더 규칙을 Claude 실험과 공유)

THINK = re.compile(r"<think>.*?</think>", re.S)


def plan(a, label: str) -> list[dict]:
    """eval_claude_batch.build와 같은 규칙으로 할 일 목록을 만든다(파일은 쓰지 않음)."""
    todo, skipped = [], []
    for typ in a.types:
        items = B.jl(B.OUT / B.TYPES[typ])[: a.limit] if a.limit else B.jl(B.OUT / B.TYPES[typ])
        gpt_agent = {r["id"]: r for r in B.jl(B.EV / B.run_name(typ, "agent", B.GPT_AGENT) / "answers.jsonl")}
        old_q = {r["id"]: r["question"] for r in B.jl(B.A_BACKUP)} if typ == "A" and B.A_BACKUP.exists() else {}
        for arm in a.arms:
            path = B.EV / B.run_name(typ, arm, label) / "answers.jsonl"
            done = {r["id"] for r in B.jl(path)} if path.exists() else set()
            for item in items:
                if item["id"] in done:
                    continue
                sources = None
                if arm == "agent":
                    row = gpt_agent.get(item["id"])
                    sources = ((row or {}).get("응답") or {}).get("sources") or []
                    asked = (row or {}).get("질문") or old_q.get(item["id"])
                    if not row or asked != item["question"] or not sources:
                        skipped.append(item["id"])
                        continue
                    system, user = B.agent_prompt(item, sources)
                else:
                    system, user = B.llm_prompt(item)
                todo.append({"type": typ, "arm": arm, "item": item, "sources": sources, "system": system, "user": user, "path": path})
    if skipped:
        print(f"건너뜀(발췌 없음·질문 다름) {len(skipped)}: {skipped[:5]}")
    return todo


def main() -> int:
    p = argparse.ArgumentParser(description="MLX 로컬 모델로 답 받기")
    p.add_argument("--model", default="mlx-community/Qwen3-14B-4bit")
    p.add_argument("--label", default="qwen3-14b-4bit", help="결과 폴더 이름에 붙는 모델 라벨")
    p.add_argument("--types", nargs="+", default=list(B.TYPES), choices=list(B.TYPES))
    p.add_argument("--arms", nargs="+", default=["llm", "agent"], choices=["llm", "agent"])
    p.add_argument("--limit", type=int, help="유형마다 앞에서 N문항만")
    p.add_argument("--think", choices=["on", "off"], default="on")
    p.add_argument("--max-tokens", type=int, default=6000)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()

    todo = plan(a, a.label)
    print(f"할 일 {len(todo)}개 · 모델 {a.model} · 생각 모드 {a.think}")
    if not todo:
        return 0

    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    mx.random.seed(a.seed)
    t0 = time.time()
    model, tok = load(a.model)
    print(f"모델 불러옴 {time.time() - t0:.0f}초, 메모리 {mx.get_active_memory() / 1e9:.1f}GB")
    think = a.think == "on"
    sampler = make_sampler(temp=0.6, top_p=0.95, top_k=20) if think else make_sampler(temp=0.7, top_p=0.8, top_k=20)
    log = B.EV / "local_mlx" / f"{a.label}_runs.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)

    for n, t in enumerate(todo, 1):
        msgs = [{"role": "system", "content": t["system"]}, {"role": "user", "content": t["user"]}]
        prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=think)
        mx.reset_peak_memory()
        start, text, last = time.time(), "", None
        for last in stream_generate(model, tok, prompt, max_tokens=a.max_tokens, sampler=sampler):
            text += last.text
        sec = time.time() - start
        reply = THINK.sub("", text).strip()
        finished = last is not None and last.finish_reason == "stop"
        it = t["item"]
        row = {"id": it["id"], "질문": it["question"], "reply": reply, "대상": a.model, "시각": datetime.now().isoformat(timespec="seconds"),
               "초": round(sec, 1), "생각 모드": a.think, "끝남": finished,
               "usage": {"input_tokens": last.prompt_tokens if last else None, "output_tokens": last.generation_tokens if last else None}}
        if t["arm"] == "agent":
            row["응답"] = {"answer": reply, "sources": t["sources"], "발췌 출처": f"{B.GPT_AGENT} 에이전트 검색 결과 재사용"}
        t["path"].parent.mkdir(parents=True, exist_ok=True)
        with t["path"].open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": it["id"], "type": t["type"], "arm": t["arm"], "초": round(sec, 1), "끝남": finished,
                                 "입력 토큰": row["usage"]["input_tokens"], "출력 토큰": row["usage"]["output_tokens"],
                                 "초당 토큰": round(last.generation_tps, 1) if last else None,
                                 "최대 메모리 GB": round(mx.get_peak_memory() / 1e9, 2), "생각 모드": a.think}, ensure_ascii=False) + "\n")
        print(f"[{n}/{len(todo)}] {t['type']} {t['arm']:5} {it['id']}  {sec:5.1f}초  출력 {row['usage']['output_tokens']}토큰"
              f"  {last.generation_tps if last else 0:.1f} tok/s  메모리 {mx.get_peak_memory() / 1e9:.1f}GB  {'' if finished else '(길이 한도에서 끊김)'}"
              f"  → {reply.splitlines()[0][:50] if reply else '(빈 답)'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
