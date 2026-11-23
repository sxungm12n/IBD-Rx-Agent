#!/usr/bin/env python3
"""CSV-RAG 조건: 문항마다 CSV 행 청크를 검색해 저장한다 (2026-11-18).

검색은 백엔드 RAG와 똑같다 (app.rag.pipeline.Engine.trace: BM25 12 + 임베딩 12 → RRF ≤20 → bge-reranker → 상위 5).
바뀌는 것은 검색 대상뿐이다: 가이드북 PDF 쪽 대신 data/RAG/IBD_insurance_csv_2024.embeddings.jsonl (CSV 44행).
검색 문장은 에이전트에 보내던 것과 같은 item['question']이다 (agent_payload.json의 answer_only: true).

API: 문항마다 질문 임베딩 1회 (text-embedding-3-large). 답 생성은 하지 않는다.
답 생성은 여기서 저장한 sources로 배치 API에 보낸다 (에이전트 답과 같은 지시문·발췌 형식).

Mac에서 직접 돈다 (리랭커가 Apple GPU(MPS)를 씀. Docker CPU로는 문항당 1~2분이라 쓰지 않는다).
백엔드 코드(backend/app/rag)를 그대로 import하고, 켜져 있는 백엔드 서버는 건드리지 않는다.
  python3.14 -m venv .venv_rag && .venv_rag/bin/pip install rank-bm25==0.2.2 openai==2.21.0 \\
      python-dotenv==1.2.3 sentence-transformers==6.2.0 faiss-cpu==1.15.1 numpy       (백엔드 requirements.txt와 같은 버전)
  RAG_EMBEDDINGS="../../../data/RAG/IBD_insurance_csv_2024.embeddings.jsonl" \\
      .venv_rag/bin/python csv_rag_retrieve.py --types A A2 C D [--limit 3]

결과: eval_out/csv_rag/retrieved_<유형>.jsonl
  id, type, question, drug_id, sources(상위 5, 에이전트 응답.sources와 같은 모양),
  rerank(상위 20 id·점수), hit_rank(정답 행 CSV-<drug_id>의 리랭크 순위, 없으면 null; D형·공통 규칙은 해당 없음)
"""
import argparse
import time
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "backend"))  # 백엔드 코드 (app.rag)
import faulthandler  # noqa: E402

import app.rag.pipeline as pipeline  # noqa: E402
from app.rag.config import ANSWER_K, EMBEDDING_MODEL, embeddings_path, openai_api_key  # noqa: E402
from app.rag.errors import GuideError  # noqa: E402
from app.rag.pipeline import Engine  # noqa: E402

STALL_SECONDS = 300  # 한 문항이 이보다 오래 걸리면 어디서 멈췄는지 로그에 남기고 끝낸다 (다시 돌리면 이어서)
_client = None


def embed_query_with_timeout(text: str):
    """backend embed.embed_query와 같은 모델·키·입력. 다른 점은 30초 제한뿐이다.
    (2026-11-18: 네트워크가 끊긴 뒤 시간 제한 없는 호출이 2시간 멈춰 있었음)"""
    global _client
    import numpy as np
    from openai import OpenAI, OpenAIError
    if _client is None:
        _client = OpenAI(api_key=openai_api_key(), timeout=30, max_retries=2)
    try:
        response = _client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    except OpenAIError as exc:
        raise GuideError(f"질문 임베딩에 실패했습니다. {exc}") from exc
    return np.asarray(response.data[0].embedding, dtype=np.float32)


pipeline.embed_query = embed_query_with_timeout

TYPES = {"A": "a_items.jsonl", "A2": "a2_items.jsonl", "C": "c_items.jsonl", "D": "d_items.jsonl"}
OUT_DIR = HERE / "eval_out" / "csv_rag"


def jl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_dict(passage) -> dict:
    return {"id": passage.id, "page": passage.page, "section": passage.section, "title": passage.title,
            "text": passage.text, "drugs": list(passage.drugs), "disease": list(passage.disease)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--types", nargs="+", default=list(TYPES), choices=list(TYPES))
    parser.add_argument("--limit", type=int, default=0, help="유형마다 앞의 N문항만 (확인용)")
    args = parser.parse_args()

    path = embeddings_path()
    if "csv" not in path.name:
        print(f"RAG_EMBEDDINGS가 CSV 임베딩이 아닙니다: {path}", file=sys.stderr)
        return 1
    engine = Engine.load()
    print(f"검색 대상 {len(engine.passages)}청크 ({path.name})", flush=True)
    ids = {p.id for p in engine.passages}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for typ in args.types:
        items = jl(HERE / "output" / TYPES[typ])
        if args.limit:
            items = items[: args.limit]
        out = OUT_DIR / (f"retrieved_{typ}_limit{args.limit}.jsonl" if args.limit else f"retrieved_{typ}.jsonl")
        done = {r["id"] for r in jl(out)} if out.exists() else set()
        hits = total = 0
        started = time.time()
        with out.open("a", encoding="utf-8") as handle:
            for n, item in enumerate(items, 1):
                if item["id"] in done:
                    continue
                faulthandler.dump_traceback_later(STALL_SECONDS + 600, exit=True)  # 재시도 대기(최대 약 10분) 포함
                for attempt in range(13):  # 질문 임베딩(API) 연결이 끊기면 최대 약 10분 기다리며 다시
                    try:
                        trace = engine.trace(item["question"])
                        break
                    except GuideError as exc:
                        if attempt == 12:
                            raise
                        print(f"  {item['id']} 재시도 {attempt + 1}: {exc}", flush=True)
                        time.sleep(min(60, 10 * (attempt + 1)))
                rerank = trace["rerank"]
                gold = f"CSV-{item.get('drug_id')}"
                hit_rank = next((h.rank for h in rerank if h.passage.id == gold), None) if gold in ids else None
                if gold in ids:
                    total += 1
                    hits += hit_rank is not None and hit_rank <= ANSWER_K
                row = {
                    "id": item["id"], "type": typ, "question": item["question"], "drug_id": item.get("drug_id"),
                    "sources": [source_dict(h.passage) for h in rerank[:ANSWER_K]],
                    "rerank": [[h.passage.id, round(h.score, 4)] for h in rerank],
                    "hit_rank": hit_rank,
                    "embeddings": path.name,
                }
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                if n % 20 == 0:
                    print(f"  {typ} {n}/{len(items)}", flush=True)
        rate = f"{hits}/{total}" if total else "해당 없음"
        print(f"{typ}: {out.name} (이번 실행 정답 행 상위 {ANSWER_K} 포함 {rate}, {time.time() - started:.0f}초)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
