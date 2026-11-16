#!/usr/bin/env python3
"""답하는 모델 비교표: gpt-5.6-terra vs Claude (API 없음, 저장된 채점 결과만, 2026-11-16).

같은 문항·같은 지시문·같은 발췌(에이전트는 gpt 에이전트가 검색한 5쪽 재사용)로 받은 답을 비교한다.
  A형   본 점수(금기 6문항 제외 101문항, 맞음 1·부분 0.5) · gpt-6-sol 채점 v2.1 첫 회(graded_v21.jsonl)
        → 두 모델 모두 '1회 채점'으로 맞춘다. gpt의 3회 다수결 값은 참고로 따로 적는다.
  A2형  같은 방식 (38문항)
  C형   코드 채점 정답률(198문항), 오답 위험도(risk_analysis.py와 같은 규칙)
  D형   코드 채점 완전 일치율(37문항), 문항 단위 위험도
  짝 비교: 같은 문항에서 에이전트가 기본 AI보다 나은 수 / 못한 수, 부호 검정 p
결과: eval_out/모델비교.md, 콘솔
"""
import collections
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import eval_a as E  # noqa: E402
import risk_analysis as R  # noqa: E402

OUT, EV = HERE / "output", HERE / "eval_out"
MODELS = ["gpt-5.6-terra", "claude-opus-5-5"]
ARMS = {"llm": "기본 AI", "agent": "에이전트"}
SCORE = E.SCORE


def jl(p: Path) -> dict:
    return {r["id"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())} if p.exists() else {}


def sign_p(better: int, worse: int) -> float | None:
    n = better + worse
    if not n:
        return None
    k = min(better, worse)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def llm_scores(prefix: str, items_file: str, model: str, arm: str, main_only: bool) -> dict:
    items = list(jl(OUT / items_file).values())
    if main_only:
        items = [i for i in items if not E.is_checklist(i)]
    g = jl(EV / f"{prefix}{arm}_{model}" / "graded_v21.jsonl")
    return {i["id"]: SCORE[g[i["id"]]["최종"]] for i in items if i["id"] in g}, len(items)


def majority(prefix: str, model: str, arm: str, ids) -> float | None:
    runs = [jl(EV / f"{prefix}{arm}_{model}" / f) for f in ("graded_v21.jsonl", "graded_v21_r1.jsonl", "graded_v21_r2.jsonl")]
    if not all(runs):
        return None
    vals = []
    for i in ids:
        votes = collections.Counter(r[i]["최종"] for r in runs if i in r)
        if votes:
            vals.append(SCORE[votes.most_common(1)[0][0]])
    return round(sum(vals) / len(vals), 3) if vals else None


def code_scores(prefix: str, model: str, arm: str) -> dict:
    g = jl(EV / f"{prefix}{arm}_{model}" / "graded_code.jsonl")
    return {k: 1.0 if v["최종"] == "맞음" else 0.0 for k, v in g.items()}


def main() -> int:
    lines = ["# 답하는 모델 비교 (API 없음, 저장된 채점 결과)", "",
             "- 같은 문항·같은 지시문. 에이전트는 두 모델 모두 gpt-5.6-terra 에이전트가 검색한 같은 5쪽을 받았다.",
             "- A·A2형: gpt-6-sol 채점 v2.1 **첫 회**로 맞춤 (괄호는 gpt 3회 다수결). C·D형: 코드 채점.", ""]
    rows = []
    for typ, prefix, items_file, kind in (("A (본 점수 101)", "", "a_items.jsonl", "llm"), ("A2", "a2_", "a2_items.jsonl", "llm"),
                                           ("C", "c_", "c_items.jsonl", "code"), ("D", "d_", "d_items.jsonl", "code")):
        for model in MODELS:
            s = {}
            n_items = None
            for arm in ARMS:
                if kind == "llm":
                    s[arm], n_items = llm_scores(prefix, items_file, model, arm, typ.startswith("A ("))
                else:
                    s[arm] = code_scores(prefix, model, arm)
                    n_items = len(jl(OUT / items_file))
            both = sorted(set(s["llm"]) & set(s["agent"]))
            if not both:
                continue
            mean = {arm: round(sum(s[arm][i] for i in both) / len(both), 3) for arm in ARMS}
            better = sum(s["agent"][i] > s["llm"][i] for i in both)
            worse = sum(s["agent"][i] < s["llm"][i] for i in both)
            maj = ""
            if kind == "llm":
                m = {arm: majority(prefix, model, arm, both) for arm in ARMS}
                if all(v is not None for v in m.values()):
                    maj = f" (다수결 {m['llm']} → {m['agent']})"
            p = sign_p(better, worse)
            rows.append(f"| {typ} | {model} | {len(both)}/{n_items} | {mean['llm']} | {mean['agent']} | {mean['agent'] - mean['llm']:+.3f}{maj} "
                        f"| {better} / {worse} | {p:.2g} |" if p is not None else
                        f"| {typ} | {model} | {len(both)}/{n_items} | {mean['llm']} | {mean['agent']} | {mean['agent'] - mean['llm']:+.3f}{maj} | {better} / {worse} | – |")
    lines += ["## 정확도", "", "| 유형 | 모델 | 비교 문항 | 기본 AI | 에이전트 | 차이 | 에이전트가 나음 / 못함 | 부호 검정 p |",
              "|---|---|---|---|---|---|---|---|", *rows, ""]

    lines += ["## 오답 위험도 (risk_analysis.py와 같은 규칙)", "",
              "| 유형 | 모델 | 대상 | 오답 | 높음·안전 | 중간·삭감 | 중간·지연 | 낮음·보류 |", "|---|---|---|---|---|---|---|---|"]
    safety = []
    for model in MODELS:
        for arm, side in ARMS.items():
            run = f"{arm}_{model}"
            if not (EV / f"c_{run}" / "graded_code.jsonl").exists():
                continue
            c = R.c_rows(side, run)
            t = collections.Counter(r["위험도"] for r in c)
            lines.append(f"| C | {model} | {side} | {len(c)} | " + " | ".join(str(t[lv]) for lv in R.LEVELS) + " |")
            if (EV / f"d_{run}" / "graded_code.jsonl").exists():
                d = R.d_rows(side, run)
                t = collections.Counter(r["위험도"] for r in d)
                lines.append(f"| D | {model} | {side} | {len(d)} | " + " | ".join(str(t[lv]) for lv in R.LEVELS) + " |")
                safety += [(model, side, r["id"], ", ".join(e["약"] for e in r["사건"] if e["위험도"] == R.LEVELS[0]))
                           for r in d if r["위험도"] == R.LEVELS[0]]
            safety += [(model, side, r["id"], r["결정 기준"]) for r in c if r["위험도"] == R.LEVELS[0]]
    lines += ["", "### '높음 · 안전' 문항", "", "| 모델 | 대상 | 문항 | 내용 |", "|---|---|---|---|",
              *[f"| {m} | {s} | {i} | {x} |" for m, s, i, x in safety], ""]

    # gpt 에이전트의 안전 오답 문항에서 Claude 에이전트는 어떻게 답했나 (같은 발췌)
    gpt_safe = {i for m, s, i, _ in safety if m == MODELS[0] and s == "에이전트"}
    if gpt_safe:
        lines += ["### gpt 에이전트 안전 오답 문항에서 Claude 에이전트 (같은 발췌)", "", "| 문항 | Claude 판정 |", "|---|---|"]
        for i in sorted(gpt_safe):
            g = jl(EV / f"{'c' if i.startswith('C-') else 'd'}_agent_{MODELS[1]}" / "graded_code.jsonl").get(i)
            lines.append(f"| {i} | {g['최종'] if g else '답 없음'} |")
        lines.append("")

    usage = [json.loads((p / "usage.json").read_text()) for p in (EV / "claude_batch").glob("*") if (p / "usage.json").exists()]
    if usage:
        lines += ["## Claude 답 비용 (배치)", "",
                  f"- 입력 {sum(u['input_tokens'] for u in usage):,} 토큰 · 출력 {sum(u['output_tokens'] for u in usage):,} 토큰 · "
                  f"약 ${sum(u['cost_usd'] for u in usage):.2f}", ""]
    text = "\n".join(lines)
    (EV / "모델비교.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
