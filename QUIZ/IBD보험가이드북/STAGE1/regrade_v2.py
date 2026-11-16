#!/usr/bin/env python3
"""A형 재채점 v2 — 원문을 받는 채점자.

기존 eval_a.py(채점 v1)는 건드리지 않는다. 저장된 답(answers.jsonl)을 그대로 두고 채점만 다시 한다.
v1과의 차이:
  1) 채점자가 문항의 원문 쪽(source_page)을 함께 받는다 → 덧붙인 내용이 원문에 있는지 직접 확인
  2) 척도 범위(Mayo 0~12, 내시경 0~3 등)를 알려 "6점 이상"="6~12"를 같은 뜻으로 본다
  3) 판정마다 '덧붙인 내용'을 따로 분류한다(원문에 있음 / 없음) → 감점 사유를 사후 감사 가능
  4) --repeat N: 같은 답을 N번 채점해 채점자 자체 일관성(self-agreement)을 잰다
결과: eval_out/<run>/graded_v2[_rK].jsonl, regrade_v2_report.md
사용: python3 STAGE1/regrade_v2.py --run agent_gpt-5.6-terra [--repeat 3] [--dry-run]
"""
import argparse, collections, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_a as E  # noqa: E402

HERE = E.HERE
CORPUS = HERE.parents[2] / "data" / "RAG" / "IBD_insurance_guide_2024.jsonl"

JUDGE_V2_SYSTEM = E.JUDGE_SYSTEM.replace(
    "급여 기준을 스스로 다시 판단하지 마세요.",
    "정답과 채점 열쇠가 기준입니다. 다만 아래 '척도 범위'와 '원문 발췌'는 사실 확인에만 쓰세요.",
) + """
추가 규칙 (v2)
- 입력의 '원문 발췌'는 가이드북 해당 쪽입니다. 답에 정답에 없는 내용이 덧붙어 있으면 그 내용이 발췌에 실제로 적혀 있는지 확인해 '덧붙인 내용'에 분류합니다.
  · 발췌에 있고 질문에 대한 답과 모순되지 않으면 '원문에 있음' → 감점하지 않습니다.
  · 발췌에 없거나 정답과 모순되면 '원문에 없음' → 지어낸 내용이므로 틀림(정답 요소를 모두 맞혔어도).
- 척도 범위: Mayo 총점 0~12, Mayo 내시경 subscore 0~3, 직장출혈 subscore 0~3, CDAI 0~약 600. 최대값이 정해진 척도에서 'N점 이상'과 'N~최대값'은 같은 뜻입니다. 단 정답이 '초과'인 경우(PUCAI > 45)는 '이상'과 다릅니다.
- 답이 정답과 같은 뜻인지는 정답·열쇠로 판단하고, 원문 발췌를 근거로 정답을 바꾸지 마세요.
- 덧붙인 내용이 없으면 '덧붙인 내용' 배열은 비워 둡니다.

채점 규칙 (v2.1, 2026-11-10 확정)
- 평가 시점(예: '4회 투약 후', '16주 동안 투약 후')은 핵심 요소가 아닙니다. 척도·값·비교·결합이 모두 맞고 평가 시점만 틀리거나 빠졌으면 부분입니다.
- 하한을 묻는 문항에서 '이상'의 여집합 표현은, 그 결과(투여 불가·보류 등)를 함께 밝힌 경우에만 같은 뜻으로 봅니다. 예) '1×10⁹ 미만이면 투여 불가' = '1×10⁹ 이상' → 맞음. 결과 없이 'N 미만'만 쓴 답은 비교 방향이 반대인 것으로 보고 틀림입니다.
- 채점 열쇠의 '함께 써도 정답'에 있는 내용은 답에 없어도 감점하지 않고, 있어도 감점하지 않습니다.
"""
VERSION = "v2.1"

# A2형에만 덧붙이는 열쇠 설명 (A형 채점 프롬프트는 v2.1 그대로). A2형 채점 기록의 '채점 버전'은 v2.1+A2.
A2_RULES = """
A2형 열쇠 읽는 법
- 채점 열쇠의 '필수 요소'가 채점할 요소 목록입니다. 요소마다 답에 같은 뜻이 있는지 봅니다. 모두 있으면 맞음, 일부만 있으면 부분, 하나도 없으면 틀림. 요소 안의 숫자·기간·횟수·용량이 다르면 그 요소는 틀림입니다.
- '이전 약제 채점'이 있으면 이전 약제 목록 요소는 그 기준대로 봅니다(계열 이름만 써도 인정, 기준에 적힌 계열이 하나라도 빠지면 그 요소는 틀림).
- '비고'와 '참고(필수 아님)'는 채점하지 않습니다.
"""

SCHEMA_V2 = json.loads(json.dumps(E.JUDGE_SCHEMA))
SCHEMA_V2["properties"]["덧붙인 내용"] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"내용": {"type": "string"}, "원문에 있음": {"type": "boolean"}},
        "required": ["내용", "원문에 있음"],
        "additionalProperties": False,
    },
}
SCHEMA_V2["required"].append("덧붙인 내용")


def load_corpus():
    pages = collections.defaultdict(list)
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            pages[int(row["page"])].append(row["text"])
    return pages


def source_text(item, pages):
    nums = [int(n) for n in re.findall(r"p\.(\d+)", item.get("source_page", ""))]
    out = []
    for n in dict.fromkeys(nums):
        out.append(f"[p.{n}]\n" + "\n---\n".join(pages.get(n, ["(코퍼스에 없음)"])))
    return "\n\n".join(out)


def judge_v2(env, item, answer, pages):
    gold = item["answer"]
    user = json.dumps({
        "질문": item["question"], "정답": gold["정답"], "형식": gold["형식"],
        "채점 열쇠": gold["채점"], "원문 발췌": source_text(item, pages), "채점할 답": answer,
    }, ensure_ascii=False, indent=1)
    system = JUDGE_V2_SYSTEM + (A2_RULES if item.get("type") == "A2" else "")
    res = json.loads(E.openai_text(env, env["EVAL_JUDGE_MODEL"], system, user, schema=SCHEMA_V2))
    if res.get("판정") not in ("맞음", "부분", "틀림"):
        raise E.CallError(f"형식 오류: {str(res)[:200]}")
    return res


def stale_answers(items, answers) -> list:
    """지금 질문과 다른 질문에 대한 답 id (예전 질문의 답을 새 정답지로 채점하지 않게).
    답에 '질문'이 저장돼 있으면 그것과 비교하고, 없으면(2026-10-27에 받은 답) 그때 문항 백업과 비교한다."""
    backup = HERE / "output" / "_backup_20261110" / "a_items.jsonl"
    old = E.load_jsonl(backup) if backup.exists() else {}
    stale = []
    for i in items:
        row = answers.get(i["id"])
        if not row:
            continue
        asked = row.get("질문") or (old.get(i["id"]) or {}).get("question")
        if asked is not None and asked != i["question"]:
            stale.append(i["id"])
    return stale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--items", type=Path, default=E.DEFAULT_ITEMS)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true", help="API 호출 없이 프롬프트만 점검")
    ap.add_argument("--regrade-ids", type=Path,
                    help="이 id들(JSON 목록)의 v2.1 채점 기록을 superseded 파일로 옮기고 다시 채점 (채점 열쇠만 바뀐 문항)")
    a = ap.parse_args()

    out = E.OUT_ROOT / a.run
    items = list(E.load_jsonl(a.items).values())[: a.limit]
    answers = E.load_jsonl(out / "answers.jsonl")
    pages = load_corpus()
    env = E.load_env()

    if a.dry_run:
        it = items[0]
        print((JUDGE_V2_SYSTEM + (A2_RULES if it.get("type") == "A2" else ""))[-900:]); print("----"); print(source_text(it, pages)[:600])
        miss = [i["id"] for i in items if not source_text(i, pages) or "코퍼스에 없음" in source_text(i, pages)]
        print(f"\n문항 {len(items)} / 저장된 답 {sum(i['id'] in answers for i in items)} / 원문 못 찾은 문항 {len(miss)}: {miss[:5]}")
        return 0

    if a.regrade_ids:
        redo = set(json.loads(a.regrade_ids.read_text(encoding="utf-8")))
        tag = VERSION.replace(".", "")
        for path in sorted(out.glob(f"graded_{tag}*.jsonl")):
            rows = E.load_jsonl(path)
            moved = [v for k, v in rows.items() if k in redo]
            if moved:
                with (out / f"superseded_{path.stem}.jsonl").open("a", encoding="utf-8") as fh:
                    fh.writelines(json.dumps(v, ensure_ascii=False) + "\n" for v in moved)
                E.rewrite_jsonl(path, {k: v for k, v in rows.items() if k not in redo})
                print(f"  다시 채점할 {len(moved)}건을 {path.name}에서 뺌")

    print(E.describe_key(env), "/ 채점 모델:", env["EVAL_JUDGE_MODEL"])
    for k in range(a.repeat):
        tag = VERSION.replace(".", "")
        path = out / (f"graded_{tag}.jsonl" if k == 0 else f"graded_{tag}_r{k}.jsonl")
        done = E.load_jsonl(path)
        todo = [i for i in items if i["id"] in answers and i["id"] not in done]
        # 질문이 바뀐 문항은 바뀐 질문으로 다시 받은 답만 채점한다.
        stale = set(stale_answers(items, answers))
        skipped = [i["id"] for i in todo if i["id"] in stale]
        if skipped:
            print(f"  질문이 바뀐 뒤 다시 받지 않은 답 {len(skipped)}개는 건너뜀: {skipped[:5]}…")
        todo = [i for i in todo if i["id"] not in skipped]
        res, lock = {}, E.threading.Lock()

        def job(item):
            reply = answers[item["id"]]["reply"].strip()
            rec = {"id": item["id"], "채점 대상": reply, "LLM": judge_v2(env, item, reply, pages),
                   "채점 모델": env["EVAL_JUDGE_MODEL"], "채점 버전": VERSION + ("+A2" if item.get("type") == "A2" else "")}
            E.append_jsonl(path, E.finalize(item, rec) | {"최종": rec["LLM"]["판정"]}, lock)

        errs = E.run_pool(job, todo, a.workers, f"채점 v2 #{k}")
        print(f"#{k}: {len(todo)}건 채점, 실패 {len(errs)} → {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
