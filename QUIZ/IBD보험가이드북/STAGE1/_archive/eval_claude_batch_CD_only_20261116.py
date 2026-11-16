#!/usr/bin/env python3
"""Claude 모델로 C·D형 답 받기 (Anthropic Message Batches API, 2026-11-16).

목적: gpt-5.6-terra와 같은 문항·같은 지시문·같은 발췌로 Claude 모델의 답을 받아, 상위 모델에서도
      에이전트 효과와 안전 오답(체크리스트 쪽 미검색 → 허용)이 같은지 본다.

같게 맞춘 것
  - 기본 AI: eval_a.py의 CASE_SYSTEM과 문제 문장(ask_llm과 같은 문자열)을 그대로 import해서 쓴다.
  - 에이전트: backend generate.py의 _ANSWER_STYLE(C형 case, D형 open_drugs)과 _context를 import한다.
             발췌는 새로 검색하지 않고, gpt-5.6-terra 에이전트 답에 저장된 5쪽(응답.sources)을 그대로 넣는다.
             → 두 모델은 똑같은 발췌를 받는다. 바뀌는 것은 답하는 모델뿐이다.
  - 추론 강도: medium으로 명시 (gpt-5.6-terra 기본값 medium과 맞춤. Opus 5.5 기본값도 medium).
  - temperature 등은 보내지 않는다. 최대 출력 16,000 토큰.
배치 API: 요금 50%. 모델·설정은 일반 호출과 같다. 결과 순서가 섞이므로 custom_id로 맞춘다.

사용 (build·status·fetch는 비용 없음, submit만 과금)
  .venv_claude/bin/python eval_claude_batch.py build  --tag pilot --limit 5      # 요청 파일만 만듦 (API 없음)
  .venv_claude/bin/python eval_claude_batch.py submit --tag pilot --yes          # 배치 제출 (과금)
  .venv_claude/bin/python eval_claude_batch.py status --tag pilot                # 진행 확인 (무료)
  .venv_claude/bin/python eval_claude_batch.py fetch  --tag pilot                # 결과 받아 answers.jsonl에 저장 (무료)
  python3 score_cases.py --run c_agent_claude-opus-5-5 --items output/c_items.jsonl   # 코드 채점 (API 없음)

결과 폴더: eval_out/{c,d}_{llm,agent}_<모델>/answers.jsonl (기존 gpt 결과와 같은 모양)
요청·원본 결과: eval_out/claude_batch/<tag>/
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "backend"))
import eval_a as E  # noqa: E402  (기본 AI 지시문·문제 문장, .env 읽기)
from app.rag.generate import _ANSWER_STYLE, _context  # noqa: E402  (에이전트 지시문·발췌 형식)
from app.rag.types import Passage  # noqa: E402

OUT, EV = HERE / "output", HERE / "eval_out"
BATCH_ROOT = EV / "claude_batch"
GPT_AGENT = "gpt-5.6-terra"
TYPES = {"C": "c_items.jsonl", "D": "d_items.jsonl"}
EFFORT, MAX_TOKENS = "medium", 16000
# 100만 토큰당 달러 (Anthropic 공식 정가, 2026-11 기준). 배치는 절반.
PRICE = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0)}
BATCH_DISCOUNT = 0.5


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def run_name(typ: str, arm: str, model: str) -> str:
    return f"{typ.lower()}_{arm}_{model}"


def llm_prompt(item: dict) -> tuple[str, str]:
    """eval_a.ask_llm의 C·D형 분기와 같은 문자열."""
    user = ("2024 대한장연구학회 염증성장질환 보험가이드북의 기준으로 답하세요. 정해진 형식으로만 답하세요.\n\n"
            f"문제: {item['question']}{E.answer_format(item)}")
    return E.CASE_SYSTEM, user


def agent_prompt(item: dict, sources: list[dict]) -> tuple[str, str]:
    """backend generate.generate_answer(answer_only=True, answer_style=...)와 같은 문자열."""
    passages = [Passage(id=s["id"], page=s.get("page"), section=s.get("section", ""), title=s.get("title", ""),
                        text=s["text"], drugs=tuple(s.get("drugs") or ()), disease=tuple(s.get("disease") or ()),
                        source_title="") for s in sources]
    system = _ANSWER_STYLE[E.ANSWER_STYLE[item["type"]]]
    user = f"질문:\n{item['question']}\n\n가이드북 발췌:\n{_context(passages)}"
    return system, user


def tag_dir(tag: str) -> Path:
    return BATCH_ROOT / tag


# ---------------------------------------------------------------- build (API 없음)


def build(a) -> int:
    d = tag_dir(a.tag)
    if (d / "batch.json").exists():
        print(f"이미 제출한 tag입니다: {d}. 다른 --tag를 쓰세요.", file=sys.stderr)
        return 1
    requests, mapping, skipped = [], {}, []
    for typ in a.types:
        items = jl(OUT / TYPES[typ])
        if a.limit:
            items = items[: a.limit]
        gpt_agent = {r["id"]: r for r in jl(EV / run_name(typ, "agent", GPT_AGENT) / "answers.jsonl")}
        for arm in a.arms:
            done_path = EV / run_name(typ, arm, a.model) / "answers.jsonl"
            done = {r["id"] for r in jl(done_path)} if done_path.exists() and not a.redo else set()
            for item in items:
                if item["id"] in done:
                    continue
                sources = None
                if arm == "agent":
                    row = gpt_agent.get(item["id"])
                    sources = ((row or {}).get("응답") or {}).get("sources") or []
                    if not row or row.get("질문") != item["question"] or not sources:
                        skipped.append(f"{typ} {item['id']}: gpt 에이전트 발췌 없음 또는 질문 다름")
                        continue
                    system, user = agent_prompt(item, sources)
                else:
                    system, user = llm_prompt(item)
                cid = f"{typ}-{arm}-{len(requests):04d}"
                requests.append({"custom_id": cid, "params": {
                    "model": a.model, "max_tokens": MAX_TOKENS, "output_config": {"effort": EFFORT},
                    "system": system, "messages": [{"role": "user", "content": user}]}})
                mapping[cid] = {"type": typ, "arm": arm, "id": item["id"], "question": item["question"],
                                "sources": sources}
    if not requests:
        print("보낼 요청이 없습니다 (이미 모두 답이 있음).")
        return 0
    if not a.dry:
        d.mkdir(parents=True, exist_ok=True)
    write = (lambda path, text: None) if a.dry else (lambda path, text: path.write_text(text, encoding="utf-8"))
    write(d / "requests.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests))
    write(d / "map.json", json.dumps(mapping, ensure_ascii=False, indent=1))
    chars = {}
    for r in requests:
        k = mapping[r["custom_id"]]["type"] + " " + mapping[r["custom_id"]]["arm"]
        n = len(r["params"]["system"]) + len(r["params"]["messages"][0]["content"])
        c = chars.setdefault(k, [0, 0])
        c[0] += 1
        c[1] += n
    meta = {"tag": a.tag, "model": a.model, "effort": EFFORT, "max_tokens": MAX_TOKENS, "types": a.types,
            "arms": a.arms, "limit": a.limit, "requests": len(requests), "built": datetime.now().isoformat(timespec="seconds"),
            "발췌 출처": f"eval_out/{{c,d}}_agent_{GPT_AGENT}/answers.jsonl 의 응답.sources", "건너뜀": skipped}
    write(d / "meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"[{a.tag}] 요청 {len(requests)}개" + (" (미리보기, 파일 안 씀)" if a.dry else f" → {d / 'requests.jsonl'}"))
    for k, (n, c) in sorted(chars.items()):
        print(f"  {k:8} {n:3}개  입력 평균 {c // n:5,}자")
    if skipped:
        print(f"  건너뜀 {len(skipped)}개: {skipped[:3]}")
    total_chars = sum(c for _, c in chars.values())
    pin, pout = PRICE.get(a.model, (None, None))
    if pin:
        # 한국어는 글자당 토큰 수가 일정하지 않아, 글자 1개 = 토큰 0.7~1.2개로 범위를 잡는다. 출력은 생각 토큰 포함 1천~3천.
        lo = (total_chars * 0.7 * pin + len(requests) * 1000 * pout) / 1e6 * BATCH_DISCOUNT
        hi = (total_chars * 1.2 * pin + len(requests) * 3000 * pout) / 1e6 * BATCH_DISCOUNT
        print(f"  예상 비용(배치 50% 반영, 거친 추정): ${lo:.2f} ~ ${hi:.2f}")
    print("API는 쓰지 않았습니다. 제출은 submit --yes.")
    return 0


# ---------------------------------------------------------------- submit / status / fetch (API)


def client():
    import anthropic
    key = E.load_env().get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ANTHROPIC_API_KEY가 없습니다. STAGE1/.env 또는 IBD보험가이드북/.env에 넣어 주세요.", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=key)


def submit(a) -> int:
    d = tag_dir(a.tag)
    if (d / "batch.json").exists():
        print(f"이미 제출했습니다: {json.loads((d / 'batch.json').read_text())['id']}", file=sys.stderr)
        return 1
    reqs = jl(d / "requests.jsonl")
    if not a.yes:
        print(f"요청 {len(reqs)}개를 제출하면 과금됩니다. 확인했으면 --yes를 붙이세요.")
        return 1
    batch = client().messages.batches.create(requests=reqs)
    (d / "batch.json").write_text(json.dumps({"id": batch.id, "submitted": datetime.now().isoformat(timespec="seconds"),
                                              "requests": len(reqs)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"제출함: {batch.id}  상태 {batch.processing_status}")
    return 0


def status(a) -> int:
    bid = json.loads((tag_dir(a.tag) / "batch.json").read_text())["id"]
    b = client().messages.batches.retrieve(bid)
    print(f"{bid}  {b.processing_status}  {b.request_counts}")
    return 0


def fetch(a) -> int:
    d = tag_dir(a.tag)
    meta, mapping = json.loads((d / "meta.json").read_text()), json.loads((d / "map.json").read_text())
    bid = json.loads((d / "batch.json").read_text())["id"]
    c = client()
    b = c.messages.batches.retrieve(bid)
    if b.processing_status != "ended":
        print(f"아직 끝나지 않음: {b.processing_status} {b.request_counts}")
        return 1
    raw, rows, failed = [], {}, []
    usage = {"input_tokens": 0, "output_tokens": 0}
    for r in c.messages.batches.results(bid):
        raw.append(r.to_dict())
        m = mapping[r.custom_id]
        if r.result.type != "succeeded":
            failed.append({"custom_id": r.custom_id, "id": m["id"], "결과": r.result.type})
            continue
        msg = r.result.message
        usage["input_tokens"] += msg.usage.input_tokens
        usage["output_tokens"] += msg.usage.output_tokens
        text = "".join(blk.text for blk in msg.content if blk.type == "text").strip()
        if msg.stop_reason != "end_turn" or not text:
            failed.append({"custom_id": r.custom_id, "id": m["id"], "결과": f"stop_reason={msg.stop_reason}, 글자 {len(text)}"})
            continue
        row = {"id": m["id"], "질문": m["question"], "reply": text, "대상": meta["model"],
               "시각": datetime.now().isoformat(timespec="seconds"), "batch": bid, "custom_id": r.custom_id,
               "effort": meta["effort"], "usage": {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}}
        if m["arm"] == "agent":
            row["응답"] = {"answer": text, "sources": m["sources"], "발췌 출처": f"{GPT_AGENT} 에이전트 검색 결과 재사용"}
        rows.setdefault(run_name(m["type"], m["arm"], meta["model"]), {})[m["id"]] = row
    (d / "results_raw.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in raw), encoding="utf-8")
    (d / "failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
    for run, new in rows.items():
        path = EV / run / "answers.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        old = {r["id"]: r for r in jl(path)} if path.exists() else {}
        old.update(new)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old.values()), encoding="utf-8")
        print(f"{run}: 새 답 {len(new)}개 저장 (총 {len(old)}개)")
    print(f"실패·이상 {len(failed)}개 → {d / 'failed.json'}")
    pin, pout = PRICE.get(meta["model"], (0, 0))
    cost = (usage["input_tokens"] * pin + usage["output_tokens"] * pout) / 1e6 * BATCH_DISCOUNT
    print(f"토큰 입력 {usage['input_tokens']:,} · 출력 {usage['output_tokens']:,}  → 비용 약 ${cost:.2f} (배치 할인 반영)")
    (d / "usage.json").write_text(json.dumps({**usage, "cost_usd": round(cost, 4), "requests_ok": sum(map(len, rows.values()))},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
    for run in rows:
        typ = run[0].upper()
        print(f"채점: python3 score_cases.py --run {run} --items output/{TYPES[typ]}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Claude C·D형 답 받기 (배치 API)")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="요청 파일만 만든다 (API 없음)")
    b.add_argument("--tag", required=True)
    b.add_argument("--model", default="claude-opus-5-5", choices=sorted(PRICE))
    b.add_argument("--types", nargs="+", default=["C", "D"], choices=["C", "D"])
    b.add_argument("--arms", nargs="+", default=["llm", "agent"], choices=["llm", "agent"])
    b.add_argument("--limit", type=int, help="유형마다 앞에서 N문항만 (파일럿)")
    b.add_argument("--redo", action="store_true", help="이미 답이 있는 문항도 다시")
    b.add_argument("--dry", action="store_true", help="파일을 쓰지 않고 개수·예상 비용만")
    s = sub.add_parser("submit", help="배치 제출 (과금)")
    s.add_argument("--tag", required=True)
    s.add_argument("--yes", action="store_true")
    for name in ("status", "fetch"):
        x = sub.add_parser(name)
        x.add_argument("--tag", required=True)
    a = p.parse_args()
    return {"build": build, "submit": submit, "status": status, "fetch": fetch}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
