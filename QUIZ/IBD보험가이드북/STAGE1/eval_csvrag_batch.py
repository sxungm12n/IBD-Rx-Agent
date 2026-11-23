#!/usr/bin/env python3
"""CSV-RAG 조건 답 받기: gpt-5.6-terra를 OpenAI Batch API로 (요금 50%, 2026-11-18).

세 번째 평가 조건. 바뀌는 것은 발췌의 출처뿐이다.
  기본 AI (llm)        : 발췌 없음
  RAG 에이전트 (agent) : 가이드북 PDF 쪽 상위 5 (백엔드 /api/guide/ask)
  CSV-RAG (csvrag)     : CSV 행 청크 상위 5 (csv_rag_retrieve.py가 같은 BM25·임베딩·RRF·리랭커로 검색)

같게 맞춘 것
  - 지시문·발췌 형식: backend generate.py의 _ANSWER_ONLY / _ANSWER_STYLE / _context
    (eval_claude_batch.agent_prompt를 그대로 씀. C형 case, D형 open_drugs, A·A2형 단답)
  - 모델·설정: gpt-5.6-terra, Responses API, 그 밖의 설정은 기본값 (백엔드 generate_answer와 같음)
  - 문항: output/{a,a2,c,d}_items.jsonl. 검색 때 저장한 질문과 지금 질문이 다르면 건너뜀.

사용 (build·status·fetch는 무료, submit만 과금)
  .venv_rag/bin/python eval_csvrag_batch.py build  --tag csvrag_full [--limit 2] [--dry]
  .venv_rag/bin/python eval_csvrag_batch.py submit --tag csvrag_full --yes
  .venv_rag/bin/python eval_csvrag_batch.py status --tag csvrag_full
  .venv_rag/bin/python eval_csvrag_batch.py fetch  --tag csvrag_full
그다음 채점: C·D형 score_cases.py (무료), A·A2형 regrade_v2_batch.py (gpt-6-sol, 과금)

--arm llm-same: 발췌 없는 기본 AI를 RAG와 같은 지시문 틀로 (eval_claude_batch.no_rag_prompt, 2026-11-23).
  .venv_rag/bin/python eval_csvrag_batch.py build --arm llm-same --tag llm_same_full
결과: eval_out/{,a2_,c_,d_}<arm>_gpt-5.6-terra/answers.jsonl (기존 에이전트 답과 같은 모양, 응답.sources에 CSV 행)
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
from eval_claude_batch import agent_prompt, jl, no_rag_prompt  # noqa: E402  (백엔드 지시문·발췌 형식 그대로)
from regrade_v2_batch import client, output_text  # noqa: E402

EV = HERE / "eval_out"
BATCH_ROOT = EV / "openai_batch"
RETRIEVED = EV / "csv_rag"
MODEL = "gpt-5.6-terra"
ARMS = {"csvrag": "CSV-RAG", "llm-same": "발췌 없음 (RAG와 같은 지시문 틀)"}
TYPES = {"A": "a_items.jsonl", "A2": "a2_items.jsonl", "C": "c_items.jsonl", "D": "d_items.jsonl"}
RUN_PREFIX = {"A": "", "A2": "a2_", "C": "c_", "D": "d_"}


def run_name(typ: str, arm: str) -> str:
    return f"{RUN_PREFIX[typ]}{arm}_{MODEL}"


def build(a) -> int:
    d = BATCH_ROOT / a.tag
    if (d / "batch.json").exists():
        print(f"이미 제출한 tag: {d}", file=sys.stderr)
        return 1
    lines, mapping, report, skipped = [], {}, [], []
    for typ in a.types:
        items = jl(HERE / "output" / TYPES[typ])
        if a.limit:
            items = items[: a.limit]
        found = {r["id"]: r for r in jl(RETRIEVED / f"retrieved_{typ}.jsonl")} if (RETRIEVED / f"retrieved_{typ}.jsonl").exists() else {}
        done_path = EV / run_name(typ, a.arm) / "answers.jsonl"
        done = {r["id"] for r in jl(done_path)} if done_path.exists() else set()
        n = 0
        for item in items:
            if item["id"] in done:
                continue
            if a.arm == "llm-same":
                got = {"sources": [], "hit_rank": None}
                system, user = no_rag_prompt(item)
            else:
                got = found.get(item["id"])
                if not got or got["question"] != item["question"] or not got["sources"]:
                    skipped.append(f"{typ} {item['id']}: 검색 결과 없음 또는 질문 다름")
                    continue
                system, user = agent_prompt(item, got["sources"])
            cid = f"r{len(lines):05d}"
            lines.append({"custom_id": cid, "method": "POST", "url": "/v1/responses",
                          "body": {"model": MODEL, "input": [{"role": "system", "content": system},
                                                             {"role": "user", "content": user}]}})
            mapping[cid] = {"type": typ, "id": item["id"], "question": item["question"], "sources": got["sources"],
                            "hit_rank": got.get("hit_rank")}
            n += 1
        report.append(f"  {typ:2}: 요청 {n} (이미 답 {len(done)})")
    chars = sum(len(json.dumps(x["body"]["input"], ensure_ascii=False)) for x in lines)
    print(f"[{a.tag}] 요청 {len(lines)}개 · 모델 {MODEL}")
    print("\n".join(report))
    if skipped:
        print(f"  건너뜀 {len(skipped)}개: {skipped[:3]}")
    if lines:
        print(f"  입력 약 {chars:,}자 (한국어 1자 ≈ 0.7~1.2토큰 → 약 {chars * 0.7 / 1e6:.2f}~{chars * 1.2 / 1e6:.2f}M 토큰)")
    if a.dry or not lines:
        print("파일을 쓰지 않았습니다 (미리보기)." if a.dry else "보낼 요청이 없습니다.")
        return 0
    d.mkdir(parents=True, exist_ok=True)
    (d / "requests.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    (d / "map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"tag": a.tag, "model": MODEL, "arm": a.arm, "types": a.types, "limit": a.limit,
                                             "requests": len(lines), "건너뜀": skipped,
                                             "발췌 출처": ARMS[a.arm] if a.arm == "llm-same" else "eval_out/csv_rag/retrieved_<유형>.jsonl (CSV 행 상위 5)",
                                             "built": datetime.now().isoformat(timespec="seconds")},
                                            ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {d}  (API 안 씀. 제출: submit --tag {a.tag} --yes)")
    return 0


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


def fetch(a) -> int:
    d = BATCH_ROOT / a.tag
    mapping = json.loads((d / "map.json").read_text())
    arm = json.loads((d / "meta.json").read_text()).get("arm", "csvrag")
    c = client()
    b = c.batches.retrieve(json.loads((d / "batch.json").read_text())["id"])
    if b.status != "completed":
        print(f"아직 끝나지 않음: {b.status} {b.request_counts}")
        return 1
    raw = c.files.content(b.output_file_id).text if b.output_file_id else ""
    (d / "results_raw.jsonl").write_text(raw, encoding="utf-8")
    if b.error_file_id:
        (d / "errors_raw.jsonl").write_text(c.files.content(b.error_file_id).text, encoding="utf-8")
    rows, failed = {}, []
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
        text = output_text(body).strip() if resp.get("status_code") == 200 else ""
        if not text:
            failed.append({"custom_id": r["custom_id"], "id": m["id"], "오류": f"HTTP {resp.get('status_code')} {str(r.get('error'))[:200]}"})
            continue
        rows.setdefault(run_name(m["type"], arm), {})[m["id"]] = {
            "id": m["id"], "질문": m["question"], "reply": text, "대상": f"{MODEL} + {ARMS[arm]}",
            "시각": datetime.now().isoformat(timespec="seconds"), "batch": b.id, "custom_id": r["custom_id"],
            "usage": {"input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0)},
            "응답": {"answer": text, "sources": m["sources"], "hit_rank": m["hit_rank"], "발췌 출처": ARMS[arm]}}
    for run, new in rows.items():
        path = EV / run / "answers.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        old = {r["id"]: r for r in jl(path)} if path.exists() else {}
        old.update(new)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old.values()), encoding="utf-8")
        print(f"{run}: 새 답 {len(new)}개 저장 (총 {len(old)}개)")
    (d / "failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "usage.json").write_text(json.dumps({**usage, "requests_ok": sum(map(len, rows.values()))}, indent=1), encoding="utf-8")
    print(f"실패 {len(failed)}건 · 토큰 입력 {usage['input_tokens']:,} 출력 {usage['output_tokens']:,} (요금은 OpenAI 사용량 페이지에서 확인)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="CSV-RAG 답 받기 (OpenAI 배치)")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--tag", required=True)
    b.add_argument("--arm", default="csvrag", choices=list(ARMS), help="csvrag: CSV 행 발췌 / llm-same: 발췌 없음, RAG와 같은 지시문 틀")
    b.add_argument("--types", nargs="+", default=list(TYPES), choices=list(TYPES))
    b.add_argument("--limit", type=int, default=0, help="유형마다 앞의 N문항만 (파일럿)")
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
