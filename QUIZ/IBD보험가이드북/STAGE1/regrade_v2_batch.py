#!/usr/bin/env python3
"""A·A2형 채점 v2.1을 OpenAI Batch API로 (요금 50%, 2026-11-16).

regrade_v2.py(일반 호출)와 같은 채점이다. 바뀌는 것은 보내는 방식뿐이다.
  - 지시문: regrade_v2.JUDGE_V2_SYSTEM (+ A2형이면 A2_RULES)
  - 입력: regrade_v2.judge_v2와 같은 JSON (질문·정답·형식·채점 열쇠·원문 발췌·채점할 답)
  - 출력 형식: regrade_v2.SCHEMA_V2 (strict JSON), 모델 .env의 EVAL_JUDGE_MODEL (gpt-6-sol), 그 밖의 설정은 기본값
  - 기록: regrade_v2와 같은 모양으로 eval_out/<run>/graded_v21.jsonl (2회째부터 _r1, _r2)
  - 질문이 바뀐 뒤 다시 받지 않은 답은 regrade_v2.stale_answers와 같은 규칙으로 건너뛴다.

사용 (build·status·fetch는 무료, submit만 과금)
  .venv_claude/bin/python regrade_v2_batch.py build  --job agent_claude-opus-5-5:output/a_items.jsonl --job ...
  .venv_claude/bin/python regrade_v2_batch.py submit --tag <build가 알려 준 tag> --yes
  .venv_claude/bin/python regrade_v2_batch.py status --tag <tag>
  .venv_claude/bin/python regrade_v2_batch.py fetch  --tag <tag>
요청·원본 결과: eval_out/openai_batch/<tag>/
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eval_a as E  # noqa: E402
import regrade_v2 as R  # noqa: E402

EV = HERE / "eval_out"
BATCH_ROOT = EV / "openai_batch"
# gpt-6-sol 100만 토큰당 달러 (2차 출처 기준 정가 $2/$10, 2026-11). 배치는 절반.
PRICE = {"gpt-6-sol": (2.0, 10.0)}


def judge_request(item: dict, answer: str, pages, model: str) -> dict:
    """regrade_v2.judge_v2 → eval_a.openai_text가 보내는 payload와 같은 body."""
    gold = item["answer"]
    user = json.dumps({
        "질문": item["question"], "정답": gold["정답"], "형식": gold["형식"],
        "채점 열쇠": gold["채점"], "원문 발췌": R.source_text(item, pages), "채점할 답": answer,
    }, ensure_ascii=False, indent=1)
    system = R.JUDGE_V2_SYSTEM + (R.A2_RULES if item.get("type") == "A2" else "")
    return {"model": model,
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "text": {"format": {"type": "json_schema", "name": "grade", "schema": R.SCHEMA_V2, "strict": True}}}


def graded_path(run: str, k: int) -> Path:
    tag = R.VERSION.replace(".", "")
    return EV / run / (f"graded_{tag}.jsonl" if k == 0 else f"graded_{tag}_r{k}.jsonl")


def build(a) -> int:
    env = E.load_env()
    model = env["EVAL_JUDGE_MODEL"]
    pages = R.load_corpus()
    tag = a.tag or f"judge_{datetime.now():%Y%m%d_%H%M%S}"
    d = BATCH_ROOT / tag
    if (d / "batch.json").exists():
        print(f"이미 제출한 tag: {d}", file=sys.stderr)
        return 1
    lines, mapping, report = [], {}, []
    for job in a.job:
        run, items_file = job.split(":", 1)
        items = list(E.load_jsonl(HERE / items_file).values())
        answers = E.load_jsonl(EV / run / "answers.jsonl")
        done = E.load_jsonl(graded_path(run, a.k))
        stale = set(R.stale_answers(items, answers))
        todo = [i for i in items if i["id"] in answers and i["id"] not in done and i["id"] not in stale]
        for item in todo:
            cid = f"j{len(lines):05d}"
            lines.append({"custom_id": cid, "method": "POST", "url": "/v1/responses",
                          "body": judge_request(item, answers[item["id"]]["reply"].strip(), pages, model)})
            mapping[cid] = {"run": run, "items": items_file, "id": item["id"]}
        report.append(f"  {run}: 채점할 답 {len(todo)} (이미 채점 {len(done)}, 질문 바뀜 {len(stale)})")
    chars = sum(len(json.dumps(x["body"]["input"], ensure_ascii=False)) for x in lines)
    print(f"[{tag}] 요청 {len(lines)}개 · 채점 모델 {model} · 기록 파일 {graded_path('<run>', a.k).name}")
    print("\n".join(report))
    if model in PRICE and lines:
        pin, pout = PRICE[model]
        lo = (chars * 0.9 * pin + len(lines) * 800 * pout) / 1e6 * 0.5
        hi = (chars * 1.2 * pin + len(lines) * 2000 * pout) / 1e6 * 0.5
        print(f"  예상 비용(배치 50%, 거친 추정): ${lo:.2f} ~ ${hi:.2f}")
    if a.dry or not lines:
        print("파일을 쓰지 않았습니다 (미리보기)." if a.dry else "보낼 요청이 없습니다.")
        return 0
    d.mkdir(parents=True, exist_ok=True)
    (d / "requests.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    (d / "map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"tag": tag, "model": model, "version": R.VERSION, "k": a.k, "jobs": a.job,
                                             "requests": len(lines), "built": datetime.now().isoformat(timespec="seconds")},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {d}  (API 안 씀. 제출: submit --tag {tag} --yes)")
    return 0


def client():
    from openai import OpenAI
    key = E.load_env().get("OPENAI_API_KEY", "")
    if not key:
        sys.exit("OPENAI_API_KEY 없음")
    return OpenAI(api_key=key)


def submit(a) -> int:
    d = BATCH_ROOT / a.tag
    if (d / "batch.json").exists():
        print("이미 제출함", file=sys.stderr)
        return 1
    n = sum(1 for _ in (d / "requests.jsonl").open(encoding="utf-8"))
    if not a.yes:
        print(f"요청 {n}개를 제출하면 과금됩니다. --yes를 붙이세요.")
        return 1
    c = client()
    f = c.files.create(file=(d / "requests.jsonl").open("rb"), purpose="batch")
    b = c.batches.create(input_file_id=f.id, endpoint="/v1/responses", completion_window="24h")
    (d / "batch.json").write_text(json.dumps({"id": b.id, "input_file_id": f.id, "requests": n,
                                              "submitted": datetime.now().isoformat(timespec="seconds")}, indent=1), encoding="utf-8")
    print(f"제출함: {b.id}  상태 {b.status}")
    return 0


def status(a) -> int:
    bid = json.loads((BATCH_ROOT / a.tag / "batch.json").read_text())["id"]
    b = client().batches.retrieve(bid)
    print(f"{bid}  {b.status}  {b.request_counts}")
    return 0


def output_text(body: dict) -> str:
    """eval_a.openai_text와 같은 규칙으로 응답 본문에서 글자를 꺼낸다."""
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    return "".join(part.get("text", "") for item in body.get("output", []) if item.get("type") == "message"
                   for part in item.get("content", []) if part.get("type") in ("output_text", "text"))


def fetch(a) -> int:
    d = BATCH_ROOT / a.tag
    meta, mapping = json.loads((d / "meta.json").read_text()), json.loads((d / "map.json").read_text())
    c = client()
    b = c.batches.retrieve(json.loads((d / "batch.json").read_text())["id"])
    if b.status != "completed":
        print(f"아직 끝나지 않음: {b.status} {b.request_counts}")
        return 1
    raw = c.files.content(b.output_file_id).text if b.output_file_id else ""
    (d / "results_raw.jsonl").write_text(raw, encoding="utf-8")
    if b.error_file_id:
        (d / "errors_raw.jsonl").write_text(c.files.content(b.error_file_id).text, encoding="utf-8")
    items_cache, out, failed = {}, {}, []
    usage = {"input_tokens": 0, "output_tokens": 0}
    for line in raw.splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        m = mapping[r["custom_id"]]
        resp = r.get("response") or {}
        body = resp.get("body") or {}
        u = body.get("usage") or {}
        usage["input_tokens"] += u.get("input_tokens", 0)
        usage["output_tokens"] += u.get("output_tokens", 0)
        try:
            if resp.get("status_code") != 200:
                raise ValueError(f"HTTP {resp.get('status_code')}: {str(r.get('error'))[:200]}")
            res = json.loads(output_text(body))
            if res.get("판정") not in ("맞음", "부분", "틀림"):
                raise ValueError(f"형식 오류: {str(res)[:200]}")
        except (ValueError, json.JSONDecodeError) as exc:
            failed.append({"custom_id": r["custom_id"], **m, "오류": str(exc)})
            continue
        items = items_cache.setdefault(m["items"], E.load_jsonl(HERE / m["items"]))
        item = items[m["id"]]
        answers = E.load_jsonl(EV / m["run"] / "answers.jsonl")
        rec = {"id": item["id"], "채점 대상": answers[item["id"]]["reply"].strip(), "LLM": res,
               "채점 모델": meta["model"], "채점 버전": R.VERSION + ("+A2" if item.get("type") == "A2" else ""),
               "채점 방식": "OpenAI Batch API", "batch": b.id}
        out.setdefault(m["run"], []).append(E.finalize(item, rec) | {"최종": res["판정"]})
    for run, recs in out.items():
        path = graded_path(run, meta["k"])
        with path.open("a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in recs)
        print(f"{run}: 채점 {len(recs)}건 → {path.name}")
    (d / "failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
    pin, pout = PRICE.get(meta["model"], (0, 0))
    cost = (usage["input_tokens"] * pin + usage["output_tokens"] * pout) / 1e6 * 0.5
    (d / "usage.json").write_text(json.dumps({**usage, "cost_usd": round(cost, 4)}, indent=1), encoding="utf-8")
    print(f"실패 {len(failed)}건 · 토큰 입력 {usage['input_tokens']:,} 출력 {usage['output_tokens']:,} → 약 ${cost:.2f} (배치)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="채점 v2.1 OpenAI 배치")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--job", action="append", required=True, help="run:items 예) agent_claude-opus-5-5:output/a_items.jsonl")
    b.add_argument("--k", type=int, default=0, help="몇 번째 채점인지 (0 → graded_v21.jsonl, 1 → _r1 …)")
    b.add_argument("--tag")
    b.add_argument("--dry", action="store_true")
    s = sub.add_parser("submit")
    s.add_argument("--tag", required=True)
    s.add_argument("--yes", action="store_true")
    for name in ("status", "fetch"):
        x = sub.add_parser(name)
        x.add_argument("--tag", required=True)
    a = p.parse_args()
    return {"build": build, "submit": submit, "status": status, "fetch": fetch}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
