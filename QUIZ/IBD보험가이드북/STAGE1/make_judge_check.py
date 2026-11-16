#!/usr/bin/env python3
"""LLM 채점자(v2.1, 3회 다수결) 검증표: 임상의가 채점자 판정을 보지 않고 모델 답을 직접 채점한다. API 없음 (2026-11-12).

표본 (실행 폴더마다)
  - 채점자 3회 판정이 갈린 답 전부
  - 다수결이 '부분'인 답 전부
  - 나머지는 기준별 20% (올림, 최소 1개, 시드 고정)
  지금 질문과 다른 질문에 대한 답(질문이 바뀐 뒤 다시 받지 않은 답)은 넣지 않는다.
눈가림
  - 임상의 파일에는 채점자 판정·이유와 답의 출처(기본 AI / 에이전트)를 넣지 않는다. 답은 무작위 순서, '답 번호'만 보인다.
  - 채점자 판정은 따로 key 파일(json)에 둔다. 임상의에게 주지 않는다.
일치도
  python3 STAGE1/make_judge_check.py score <key.json> <임상의1.xlsx> [<임상의2.xlsx>]
  → 사람–채점자 일치율·Cohen κ·가중 κ(선형), 두 사람이면 사람–사람 κ.
사용
  python3 STAGE1/make_judge_check.py build --runs llm_gpt-5.6-terra agent_gpt-5.6-terra --items STAGE1/output/a_items.jsonl \
      --out STAGE1/output/채점자검증표.xlsx --key STAGE1/output/채점자검증_key.json
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eval_a as E  # noqa: E402
import regrade_v2 as R  # noqa: E402

LABELS = ["맞음", "부분", "틀림"]
TAG = R.VERSION.replace(".", "")


def majority(reps: list[dict], iid: str) -> tuple[str | None, bool]:
    votes = [r[iid]["최종"] for r in reps if iid in r]
    if len(votes) < 3:
        return None, False
    top, n = collections.Counter(votes).most_common(1)[0]
    score = {"맞음": 1, "부분": 0.5, "틀림": 0}
    med = sorted(votes, key=lambda v: score[v])[len(votes) // 2]  # 셋 다 다르면 중앙값 (_archive/scripts/compare_v2.py와 같음)
    return (top if n >= 2 else med), len(set(votes)) > 1


def build(a) -> int:
    items = {}
    for path in a.items:
        items.update(E.load_jsonl(path))
    rng = random.Random(a.seed)
    rows, replies = [], {}
    for run in a.runs:
        out = E.OUT_ROOT / run
        answers = E.load_jsonl(out / "answers.jsonl")
        replies[run] = answers
        reps = [E.load_jsonl(out / (f"graded_{TAG}.jsonl" if k == 0 else f"graded_{TAG}_r{k}.jsonl")) for k in range(3)]
        stale = set(R.stale_answers([it for it in items.values() if it["id"] in answers], answers))
        pool = collections.defaultdict(list)
        for iid, it in items.items():
            if iid not in answers or iid in stale:
                continue
            maj, split = majority(reps, iid)
            if maj is None:
                continue
            rec = {"run": run, "id": iid, "maj": maj, "split": split, "votes": [r[iid]["최종"] for r in reps]}
            if split or maj == "부분":
                rec["why"] = "판정 갈림" if split else "부분"
                rows.append(rec)
            else:
                pool[it["기준"]].append(rec)
        for crit in sorted(pool):
            group = sorted(pool[crit], key=lambda r: r["id"])
            for rec in rng.sample(group, max(1, math.ceil(len(group) * a.rate))):
                rec["why"] = "무작위 표본"
                rows.append(rec)
    rng.shuffle(rows)
    for n, rec in enumerate(rows, 1):
        rec["no"] = n

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    g = wb.active
    g.title = "안내"
    for r, t in enumerate([
        "LLM 채점자 검증표 (임상의용)",
        "목적: 모델 답을 임상의가 직접 채점해 LLM 채점자(gpt-6-sol, 채점 규칙 v2.1, 3회 다수결)와의 일치도(κ)를 보고한다.",
        "1. '채점' 시트의 노란 칸(사람 판정, 코멘트, 검수자)만 채운다. 판정은 맞음 / 부분 / 틀림.",
        "2. 정답과 채점 열쇠를 기준으로 채점한다. '함께 써도 정답'은 써도 안 써도 감점하지 않는다. '참고(필수 아님)'·'비고'는 채점하지 않는다.",
        "3. 규칙: 평가 시점만 틀리면 부분 / 이전 치료는 반응 없음·내약성 없음·금기를 모두 써야 맞음 / 'N 미만'은 결과(투여 불가)를 함께 써야 '이상'과 같은 뜻 / 원문에 없는 조건을 덧붙이면 틀림.",
        "4. 채점자 판정과 답의 출처(어떤 AI인지)는 일부러 넣지 않았다. 두 검수자는 서로의 판정을 보지 않는다.",
    ], 1):
        c = g.cell(row=r, column=1, value=t)
        c.font = Font(name="Arial", size=12 if r == 1 else 10, bold=r == 1)
        c.alignment = Alignment(wrap_text=True)
    g.column_dimensions["A"].width = 130
    ws = wb.create_sheet("채점")
    cols = [("답 번호", 7), ("문항 ID", 22), ("기준", 12), ("질문", 40), ("정답", 40), ("채점 열쇠", 40), ("원문 쪽", 14),
            ("모델 답", 50), ("사람 판정", 10), ("코멘트", 30), ("검수자", 10)]
    yellow = PatternFill("solid", fgColor="FFFF00")
    for ci, (name, w) in enumerate(cols, 1):
        c = ws.cell(row=1, column=ci, value=name)
        c.font = Font(name="Arial", size=10, bold=True)
        ws.column_dimensions[c.column_letter].width = w
    for r, rec in enumerate(rows, 2):
        it = items[rec["id"]]
        ans = it["answer"]["정답"]
        vals = [rec["no"], rec["id"], it["기준"], it["question"], "\n".join(ans) if isinstance(ans, list) else ans,
                json.dumps(it["answer"]["채점"], ensure_ascii=False), it["source_page"],
                replies[rec["run"]][rec["id"]]["reply"].strip(), None, None, None]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=ci, value=v)
            c.font = Font(name="Arial", size=10)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if ci >= 9:
                c.fill = yellow
    dv = DataValidation(type="list", formula1='"맞음,부분,틀림"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"I2:I{len(rows) + 1}")
    ws.freeze_panes = "D2"
    wb.save(a.out)
    key = {"채점 버전": R.VERSION, "시드": a.seed, "표본 비율": a.rate,
           "답": {str(rec["no"]): {k: rec[k] for k in ("run", "id", "maj", "split", "votes", "why")} for rec in rows}}
    Path(a.key).write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    why = collections.Counter(rec["why"] for rec in rows)
    print(f"검증표 {len(rows)}행 → {a.out} / key → {a.key} / {dict(why)} / 실행별 {dict(collections.Counter(r['run'] for r in rows))}")
    return 0


def kappa(x: list[str], y: list[str], weighted: bool = False) -> float:
    n = len(x)
    idx = {k: i for i, k in enumerate(LABELS)}
    w = (lambda i, j: 1 - abs(i - j) / (len(LABELS) - 1)) if weighted else (lambda i, j: 1.0 if i == j else 0.0)
    po = sum(w(idx[a], idx[b]) for a, b in zip(x, y)) / n
    cx, cy = collections.Counter(x), collections.Counter(y)
    pe = sum(w(idx[a], idx[b]) * cx[a] * cy[b] for a in LABELS for b in LABELS) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def read_human(path: str) -> dict[str, str]:
    from openpyxl import load_workbook
    ws = load_workbook(path)["채점"]
    return {str(r[0].value): r[8].value.strip() for r in ws.iter_rows(min_row=2) if r[8].value and r[8].value.strip() in LABELS}


def score(a) -> int:
    key = json.loads(Path(a.key).read_text(encoding="utf-8"))["답"]
    humans = [read_human(p) for p in a.files]
    out = {}
    for n, h in enumerate(humans, 1):
        common = [k for k in h if k in key]
        x, y = [h[k] for k in common], [key[k]["maj"] for k in common]
        out[f"사람{n}–채점자"] = {"답 수": len(common), "일치율": round(sum(p == q for p, q in zip(x, y)) / len(common), 3),
                               "κ": round(kappa(x, y), 3), "가중 κ(선형)": round(kappa(x, y, True), 3)}
    if len(humans) == 2:
        common = [k for k in humans[0] if k in humans[1]]
        x, y = [humans[0][k] for k in common], [humans[1][k] for k in common]
        out["사람1–사람2"] = {"답 수": len(common), "일치율": round(sum(p == q for p, q in zip(x, y)) / len(common), 3),
                            "κ": round(kappa(x, y), 3), "가중 κ(선형)": round(kappa(x, y, True), 3)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM 채점자 검증표 (API 없음)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--runs", nargs="+", required=True)
    b.add_argument("--items", nargs="+", type=Path, required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--key", required=True)
    b.add_argument("--rate", type=float, default=0.2)
    b.add_argument("--seed", type=int, default=20261112)
    s = sub.add_parser("score")
    s.add_argument("key")
    s.add_argument("files", nargs="+")
    a = ap.parse_args()
    return build(a) if a.cmd == "build" else score(a)


if __name__ == "__main__":
    sys.exit(main())
