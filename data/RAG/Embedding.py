"""가이드북 JSONL의 text를 text-embedding-3-large로 임베딩한다.

실행:
    pip install openai python-dotenv
    python Embedding.py

키는 같은 폴더의 .env에 OPENAI_API_KEY로 둔다.
결과는 IBD_insurance_guide_2024.embeddings.jsonl 에 원문 필드와 벡터를 함께 쓴다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "IBD_insurance_guide_2024.jsonl"
OUTPUT = HERE / "IBD_insurance_guide_2024.embeddings.jsonl"
MODEL = "text-embedding-3-large"
BATCH_SIZE = 32


def load_records(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            text = (record.get("text") or "").strip()
            if not text:
                raise SystemExit(f"{path.name}:{line_no} text가 비어 있습니다.")
            record["text"] = text
            records.append(record)
    if not records:
        raise SystemExit(f"{path.name}에 임베딩할 기록이 없습니다.")
    return records


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=MODEL, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]


def main() -> None:
    load_dotenv(HERE / ".env")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("data/RAG/.env에 OPENAI_API_KEY를 넣어 주세요.")

    records = load_records(SOURCE)
    client = OpenAI(api_key=api_key)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8") as handle:
        for start in range(0, len(records), BATCH_SIZE):
            batch = records[start : start + BATCH_SIZE]
            vectors = embed_batch(client, [record["text"] for record in batch])
            for record, vector in zip(batch, vectors, strict=True):
                payload = dict(record)
                payload["embedding_model"] = MODEL
                payload["embedding"] = vector
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            done = min(start + BATCH_SIZE, len(records))
            print(f"{done}/{len(records)}", flush=True)

    temporary.replace(OUTPUT)
    print(f"저장: {OUTPUT}")


if __name__ == "__main__":
    main()
