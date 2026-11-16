#!/usr/bin/env python3
"""자기진화(self-evolving) RAG 에이전트 실험 — 노션 '자기진화 RAG 에이전트 평가 계획 (v2)' 구현.

ACE 방식(생성 → 반성 → 정리). 모델 가중치는 바꾸지 않고 '경험 노트(playbook)'만 고친다.
노트는 에이전트 /api/guide/ask 의 playbook 필드로 답변 프롬프트에 붙는다(검색에는 쓰지 않음).

하위 명령
  split    본 점수 101문항을 '평가 시점을 뺀 채점 열쇠' 기준 묶음(30개)으로 나눠 A/B 묶음을 만든다.
  evolve   학습 묶음으로 노트를 진화시킨다. --feedback gold(정답·원문 쪽) | self(원문 자기검증, 정답 없음)
  answer   고정된 노트로 평가 묶음에 답한다. 결과는 eval_out/<run>/answers.jsonl (regrade_v2.py로 채점)
  online   E-온라인: 평가 묶음을 풀면서 정답 없이 실시간으로 노트를 고친다.
  audit    노트에 평가 묶음의 약제명·숫자 조건이 들어 있는지 검사한다.
  compare  평가 묶음에서 두 실행의 v2.1 채점(3회 다수결)을 짝 비교한다.

원칙
  - 채점자(gpt-6-sol)는 진화에 쓰지 않는다. 진화 피드백은 정답 텍스트와 원문 쪽뿐(gold) 또는 원문뿐(self).
  - 반성·정리는 기반 모델(EVAL_TARGET_MODEL, gpt-5.6-terra)이 한다.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import random
import re
import sys
import threading
import time
from pathlib import Path

STAGE1 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STAGE1))
import eval_a as E  # noqa: E402
import regrade_v2 as R  # noqa: E402

HERE = Path(__file__).resolve().parent
SPLIT = HERE / "split.json"
DEFAULT_AGENT = "http://127.0.0.1:8001/api/guide/ask"
MAX_ENTRIES = 40          # 노트 항목 수 상한 (예비 실행 후 확정)
MAX_CHARS = 6000          # 노트 전체 글자 수 상한

# ---------------------------------------------------------------- 공통


def items_main() -> dict:
    items = E.load_jsonl(E.DEFAULT_ITEMS)
    return {k: v for k, v in items.items() if not v["기준"].startswith("금기")}


def cluster_key(item: dict) -> str:
    """평가 시점을 뺀 채점 열쇠 + 기준. 같은 키 = 같은 내용 → 같은 묶음.
    '함께 써도 정답' 중 시점 대안(다른 쪽의 시점 문구)과 고령·고위험 함정의 체크리스트 인용 허용은 내용이 아니므로 뺀다.
    (함정 활성도 문항의 '대상' 설명은 내용이 달라 그대로 둔다.)"""
    key = {k: v for k, v in item["answer"]["채점"].items() if k != "시점"}
    alt = key.get("함께 써도 정답")
    if (isinstance(alt, dict) and set(alt) <= {"시점", "이유"}) or (item["기준"].startswith("고령") and isinstance(alt, str)):
        key.pop("함께 써도 정답")
    return item["기준"] + "|" + json.dumps(key, ensure_ascii=False, sort_keys=True)


def load_split() -> dict:
    if not SPLIT.exists():
        sys.exit("split.json이 없음: 먼저 `evolve.py split`")
    return json.loads(SPLIT.read_text(encoding="utf-8"))


def fold_ids(split: dict, fold: str, part: str = "all") -> list[str]:
    f = split["folds"][fold]
    return f["train"] + f["dev"] if part == "all" else f[part]


def ask(env: dict, url: str, question: str, playbook: str | None) -> tuple[str, dict]:
    payload = {"question": question, "answer_only": True}
    if playbook:
        payload["playbook"] = playbook
    data = E.post_json(url, payload, {}, timeout=300)
    reply = (data.get("answer") or "").strip()
    if not reply:
        raise E.CallError("에이전트 답이 비어 있음")
    return reply, data


def llm_json(env: dict, system: str, user: str, schema: dict) -> dict:
    return json.loads(E.openai_text(env, env["EVAL_TARGET_MODEL"], system, user, schema=schema))


def render(playbook: list[dict]) -> str:
    return "\n".join(f"[{e['id']}] {e['text']}" for e in playbook)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- split


def cmd_split(a) -> int:
    items = items_main()
    clusters = collections.defaultdict(list)
    for iid, it in items.items():
        clusters[cluster_key(it)].append(iid)
    rng = random.Random(a.seed)
    groups = list(clusters.values())
    rng.shuffle(groups)
    groups.sort(key=len, reverse=True)  # 큰 묶음부터 배치 (같은 크기 안에서는 시드 순서)
    folds = {"A": [], "B": []}
    load = {"A": collections.Counter(), "B": collections.Counter()}
    for g in groups:
        crit = items[g[0]]["기준"]
        cls = collections.Counter(items[i]["drug_class"] for i in g)
        # 같은 기준 문항 수 → 전체 문항 수 → 약제 계열 균형 순으로 적은 쪽에 넣는다
        def cost(f):
            return (load[f][crit], sum(len(x) for x in folds[f]), sum(load[f]["cls:" + c] for c in cls))
        f = min(("A", "B"), key=cost)
        folds[f].append(g)
        load[f][crit] += len(g)
        for c, n in cls.items():
            load[f]["cls:" + c] += n
    out = {"seed": a.seed, "기준": "평가 시점을 뺀 채점 열쇠 + 기준이 같은 문항 = 한 묶음", "folds": {}}
    for f, gs in folds.items():
        gs = gs[:]
        rng.shuffle(gs)
        n_dev = max(1, round(len(gs) * 0.2))
        dev = [i for g in gs[:n_dev] for i in g]
        train = [i for g in gs[n_dev:] for i in g]
        out["folds"][f] = {"clusters": len(gs), "train": sorted(train), "dev": sorted(dev),
                           "기준별": dict(collections.Counter(items[i]["기준"] for g in gs for i in g))}
    write_json(SPLIT, out)
    for f, v in out["folds"].items():
        print(f"{f}: 묶음 {v['clusters']}개, 문항 {len(v['train']) + len(v['dev'])} (학습 {len(v['train'])} / 검증 {len(v['dev'])}) {v['기준별']}")
    # 유출 검사: 같은 묶음 키가 양쪽에 있으면 안 됨
    ka = {cluster_key(items[i]) for i in fold_ids(out, "A")}
    kb = {cluster_key(items[i]) for i in fold_ids(out, "B")}
    assert not ka & kb, "묶음 키가 양쪽에 있음"
    print("유출 검사 통과: A/B가 공유하는 기준 묶음 없음 →", SPLIT)
    return 0


# ---------------------------------------------------------------- 반성·정리 (ACE)

REFLECT_GOLD = """당신은 보험가이드북 시험을 푼 응시자의 답을 되돌아보는 코치입니다.
입력: 질문, 응시자의 답, 정답, 정답의 근거가 된 가이드북 원문 쪽.
할 일
- 답이 정답과 같은 뜻인지, 무엇이 빠졌거나 틀렸거나 원문에 없는 내용을 덧붙였는지 진단합니다.
- 다음 문제에서도 쓸 수 있는 답변 요령(교훈)을 0~3개 씁니다. 한 약제에만 해당하는 수치를 외우는 교훈보다,
  다른 약제·문항에도 적용되는 읽기·답쓰기 요령을 우선합니다. 틀린 데가 없으면 교훈은 비워도 됩니다.
- 교훈은 한국어 한 문장씩, 가이드북 원문과 모순되면 안 됩니다."""

REFLECT_SELF = """당신은 보험가이드북 시험을 푼 응시자 자신입니다. 정답은 주어지지 않습니다.
입력: 질문, 내 답, 내가 검색해서 읽은 가이드북 발췌.
할 일
- 내 답의 각 내용이 발췌에 실제로 적혀 있는지 대조합니다. 발췌에 없는 내용, 질문이 물었는데 빠뜨린 조건(시점, 척도, 값, 비교, 결합)을 찾습니다.
- 다음 문제에서도 쓸 수 있는 답변 요령(교훈)을 0~3개 씁니다. 확신이 없으면 비웁니다.
- 교훈은 한국어 한 문장씩, 발췌와 모순되면 안 됩니다."""

REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "맞음": {"type": "boolean"},
        "진단": {"type": "string"},
        "교훈": {"type": "array", "items": {"type": "string"}},
        "도움된 노트": {"type": "array", "items": {"type": "string"}},
        "해로웠던 노트": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["맞음", "진단", "교훈", "도움된 노트", "해로웠던 노트"],
    "additionalProperties": False,
}

CURATE = f"""당신은 경험 노트를 관리하는 편집자입니다. 노트는 보험가이드북 시험에서 답을 쓸 때 참고하는 짧은 요령 목록입니다.
입력: 현재 노트(항목 [id] 문장), 새 교훈들.
할 일: 노트를 통째로 다시 쓰지 말고, 바꿀 부분만 연산으로 냅니다.
- add: 새 요령 (기존과 중복되면 넣지 않음)
- edit: 기존 항목을 더 정확하게 고침 (id와 새 문장)
- remove: 틀렸거나 중복되거나 해로운 항목 id
규칙: 항목은 한 문장, 노트 전체 {MAX_ENTRIES}개 이하. 가이드북 원문과 모순되는 내용은 넣지 않습니다."""

CURATE_SCHEMA = {
    "type": "object",
    "properties": {
        "add": {"type": "array", "items": {"type": "string"}},
        "edit": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                                            "required": ["id", "text"], "additionalProperties": False}},
        "remove": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["add", "edit", "remove"],
    "additionalProperties": False,
}


def sources_text(resp: dict) -> str:
    return "\n\n".join(f"[p.{s.get('page')}] {s.get('text', '')}" for s in resp.get("sources", []))


def reflect(env, mode: str, item: dict, reply: str, resp: dict, pages, playbook: list[dict]) -> dict:
    if mode == "gold":
        user = json.dumps({"질문": item["question"], "응시자의 답": reply, "정답": item["answer"]["정답"],
                           "원문 쪽": R.source_text(item, pages), "답할 때 붙어 있던 노트": render(playbook)},
                          ensure_ascii=False, indent=1)
        return llm_json(env, REFLECT_GOLD, user, REFLECT_SCHEMA)
    user = json.dumps({"질문": item["question"], "내 답": reply, "읽은 발췌": sources_text(resp),
                       "답할 때 붙어 있던 노트": render(playbook)}, ensure_ascii=False, indent=1)
    return llm_json(env, REFLECT_SELF, user, REFLECT_SCHEMA)


def curate(env, playbook: list[dict], lessons: list[str], counter: list[int]) -> tuple[list[dict], dict]:
    if not lessons:
        return playbook, {"add": [], "edit": [], "remove": []}
    user = json.dumps({"현재 노트": render(playbook) or "(비어 있음)", "새 교훈": lessons}, ensure_ascii=False, indent=1)
    ops = llm_json(env, CURATE, user, CURATE_SCHEMA)
    by_id = {e["id"]: e for e in playbook}
    for rid in ops["remove"]:
        by_id.pop(rid, None)
    for ed in ops["edit"]:
        if ed["id"] in by_id and ed["text"].strip():
            by_id[ed["id"]]["text"] = ed["text"].strip()
    for text in ops["add"]:
        if text.strip():
            counter[0] += 1
            by_id[f"n{counter[0]}"] = {"id": f"n{counter[0]}", "text": text.strip()}
    new = list(by_id.values())
    # 상한: 항목 수·글자 수를 넘으면 오래된 항목부터 뺀다 (기록에 남김)
    while len(new) > MAX_ENTRIES or len(render(new)) > MAX_CHARS:
        new.pop(0)
    return new, ops


# ---------------------------------------------------------------- evolve / online


def run_dir(name: str) -> Path:
    d = HERE / "runs" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def step(env, url, mode, item, playbook, pages, counter, log_path, extra=None):
    t0 = time.time()
    reply, resp = ask(env, url, item["question"], render(playbook) or None)
    ref = reflect(env, mode, item, reply, resp, pages, playbook)
    new, ops = curate(env, playbook, ref["교훈"], counter)
    rec = {"id": item["id"], "reply": reply, "reflect": ref, "ops": ops, "노트 항목 수": len(new),
           "초": round(time.time() - t0, 1), **(extra or {})}
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return new, reply, resp


def cmd_evolve(a) -> int:
    env = E.load_env()
    items = items_main()
    split = load_split()
    train = [items[i] for i in fold_ids(split, a.train, "train")][: a.limit]
    pages = R.load_corpus()
    name = a.name or f"{a.feedback}_{a.train}_r{a.run}"
    d = run_dir(name)
    log = d / "log.jsonl"
    playbook, counter = [], [0]
    rng = random.Random(1000 + a.run)
    meta = {"name": name, "feedback": a.feedback, "train_fold": a.train, "epochs": a.epochs, "run": a.run,
            "model": env["EVAL_TARGET_MODEL"], "max_entries": MAX_ENTRIES, "max_chars": MAX_CHARS,
            "agent": a.agent_url, "시작": time.strftime("%Y-%m-%dT%H:%M:%S")}
    write_json(d / "meta.json", meta)
    print(E.describe_key(env), "/ 기반 모델:", env["EVAL_TARGET_MODEL"], "/", name, f"/ 학습 {len(train)}문항 × {a.epochs}바퀴")
    for ep in range(a.epochs):
        order = train[:]
        rng.shuffle(order)
        for k, item in enumerate(order, 1):
            try:
                playbook, _, _ = step(env, a.agent_url, a.feedback, item, playbook, pages, counter, log, {"epoch": ep})
            except E.CallError as err:
                print(f"  실패 {item['id']}: {err}", file=sys.stderr)
            if k % 10 == 0 or k == len(order):
                print(f"  바퀴 {ep + 1} {k}/{len(order)} · 노트 {len(playbook)}항목 {len(render(playbook))}자", flush=True)
        write_json(d / f"playbook_ep{ep + 1}.json", playbook)
        if a.dev_eval:
            dev = [items[i] for i in fold_ids(split, a.train, "dev")]
            sc = dev_score(env, a.agent_url, dev, playbook, pages)
            with (d / "dev_scores.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"epoch": ep + 1, **sc}, ensure_ascii=False) + "\n")
            print(f"  바퀴 {ep + 1} 검증 점수 {sc['점수']:.3f} ({sc['문항']}문항)", flush=True)
    write_json(d / "playbook.json", playbook)
    meta["끝"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_json(d / "meta.json", meta)
    print("노트 고정 →", d / "playbook.json")
    return 0


def dev_score(env, url, dev: list[dict], playbook: list[dict], pages) -> dict:
    """학습 묶음 안의 검증 문항을 현재 노트로 답하고 v2.1 채점자로 1회 채점 (조기 중단 판단 기록용, API 사용)."""
    pts = []
    for item in dev:
        reply, _ = ask(env, url, item["question"], render(playbook) or None)
        res = R.judge_v2(env, item, reply, pages)
        pts.append(S[res["판정"]])
    return {"문항": len(pts), "점수": sum(pts) / len(pts) if pts else 0.0}


def save_answer(out: Path, item, reply, resp, url, lock, extra=None):
    E.append_jsonl(out / "answers.jsonl", {"id": item["id"], "reply": reply, "대상": url, "시각": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                           "응답": resp, **(extra or {})}, lock)


def cmd_answer(a) -> int:
    env = E.load_env()
    items = items_main()
    split = load_split()
    test = [items[i] for i in fold_ids(split, a.test)][: a.limit]
    pb_text = None
    if a.playbook:
        p = Path(a.playbook)
        pb_text = render(json.loads(p.read_text(encoding="utf-8"))) if p.suffix == ".json" else p.read_text(encoding="utf-8")
    out = E.OUT_ROOT / a.run
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "evolve_meta.json", {"test_fold": a.test, "playbook": a.playbook, "playbook_chars": len(pb_text or ""),
                                          "agent": a.agent_url, "model": env["EVAL_TARGET_MODEL"]})
    done = E.load_jsonl(out / "answers.jsonl")
    todo = [i for i in test if i["id"] not in done]
    lock = threading.Lock()

    def job(item):
        reply, resp = ask(env, a.agent_url, item["question"], pb_text)
        save_answer(out, item, reply, resp, a.agent_url, lock)

    errs = E.run_pool(job, todo, a.workers, "답")
    print(f"{len(todo)}건 답, 실패 {len(errs)} → {out / 'answers.jsonl'}  (채점: regrade_v2.py --run {a.run} --repeat 3)")
    return 0


def cmd_online(a) -> int:
    """E-온라인: 평가 문항을 순서대로 풀면서, 정답 없이(self) 노트를 고친다. 답은 노트 갱신 전에 기록."""
    env = E.load_env()
    items = items_main()
    split = load_split()
    test = [items[i] for i in fold_ids(split, a.test)][: a.limit]
    random.Random(2000 + a.run).shuffle(test)
    pages = R.load_corpus()
    out = E.OUT_ROOT / a.run_name
    out.mkdir(parents=True, exist_ok=True)
    d = run_dir(a.run_name)
    playbook, counter, lock = [], [0], threading.Lock()
    for k, item in enumerate(test, 1):
        try:
            playbook, reply, resp = step(env, a.agent_url, "self", item, playbook, pages, counter, d / "log.jsonl", {"순서": k})
            save_answer(out, item, reply, resp, a.agent_url, lock, {"순서": k})
        except E.CallError as err:
            print(f"  실패 {item['id']}: {err}", file=sys.stderr)
        if k % 10 == 0 or k == len(test):
            print(f"  {k}/{len(test)} · 노트 {len(playbook)}항목", flush=True)
    write_json(d / "playbook.json", playbook)
    print("답 →", out / "answers.jsonl")
    return 0


# ---------------------------------------------------------------- audit


def cmd_audit(a) -> int:
    items = items_main()
    split = load_split()
    pb = json.loads(Path(a.playbook).read_text(encoding="utf-8"))
    text = render(pb)
    test = [items[i] for i in fold_ids(split, a.test)]
    train_names = {w for i in fold_ids(split, "B" if a.test == "A" else "A") for w in re.findall(r"[A-Za-z]{4,}", items[i]["drug_name"])}
    hits = []
    for it in test:
        names = [w for w in re.findall(r"[A-Za-z]{4,}", it["drug_name"]) if w not in {"prolonged", "release"}]
        nums = {f"{v:g}" for k, v in it["answer"]["채점"].items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        for n in names:
            if re.search(rf"\b{re.escape(n)}\b", text, flags=re.I):
                hits.append({"문항": it["id"], "종류": "약제명", "값": n, "학습 묶음에도 있는 약제": n in train_names})
        unit = r"\s*(점|주|%|g/dL|cells|/mm|×10|x10|세|회|kg|mg)"
        for n in nums:
            # 숫자 뒤에 단위가 붙은 경우만 센다 ('6' 같은 흔한 숫자 과검출 방지). 그래도 사람이 확인
            if re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.]){unit}", text):
                hits.append({"문항": it["id"], "종류": "숫자+단위", "값": n})
    uniq = {(h["종류"], h["값"]) for h in hits}
    report = {"노트": a.playbook, "항목 수": len(pb), "글자 수": len(text), "평가 묶음": a.test,
              "겹친 값(고유)": sorted(map(list, uniq)), "겹친 문항 수": len({h["문항"] for h in hits}), "상세": hits}
    out = Path(a.playbook).with_name(f"audit_{a.test}.json")
    write_json(out, report)
    print(f"노트 {len(pb)}항목 / 평가 묶음 {a.test}와 겹친 값 {len(uniq)}종, 관련 문항 {report['겹친 문항 수']}개 → {out}")
    print("  (약제명이 겹쳐도 학습 묶음에도 같은 약제가 있으면 유출이 아닐 수 있음. 숫자는 사람이 확인)")
    return 0


# ---------------------------------------------------------------- compare

S = {"맞음": 1.0, "부분": 0.5, "틀림": 0.0}


def majority(run: str, tag: str = "v21") -> dict:
    reps = [E.load_jsonl(E.OUT_ROOT / run / n) for n in (f"graded_{tag}.jsonl", f"graded_{tag}_r1.jsonl", f"graded_{tag}_r2.jsonl")]
    reps = [r for r in reps if r]
    out = {}
    for i in reps[0]:
        vals = [r[i]["최종"] for r in reps if i in r]
        c = collections.Counter(vals).most_common()
        out[i] = c[0][0] if c[0][1] > len(vals) / 2 else sorted(vals, key=lambda v: S[v])[len(vals) // 2]
    return out


def cmd_compare(a) -> int:
    split = load_split()
    ids = fold_ids(split, a.test)
    x, y = majority(a.new), majority(a.base)
    ids = [i for i in ids if i in x and i in y]
    if not ids:
        sys.exit("두 실행 모두 채점된 평가 문항이 없음")
    diffs = [S[x[i]] - S[y[i]] for i in ids]
    up, dn = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    n = up + dn
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(up, dn) + 1)) / 2 ** n) if n else 1.0
    rng = random.Random(0)
    bs = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(10000))
    print(f"평가 묶음 {a.test}: {len(ids)}문항")
    print(f"  {a.base:<40} {sum(S[y[i]] for i in ids) / len(ids):.3f}")
    print(f"  {a.new:<40} {sum(S[x[i]] for i in ids) / len(ids):.3f}")
    print(f"  차이 {sum(diffs) / len(diffs):+.3f}, 95% CI [{bs[250]:+.3f}, {bs[9749]:+.3f}], 개선 {up} / 악화 {dn}, sign p={p:.2g}")
    by = collections.defaultdict(list)
    items = items_main()
    for i, dlt in zip(ids, diffs):
        by[items[i]["기준"]].append(dlt)
    for k, v in by.items():
        print(f"    {k:<12} {len(v):>3}문항  {sum(v) / len(v):+.3f}")
    return 0


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split"); s.add_argument("--seed", type=int, default=20261110)
    s = sub.add_parser("evolve")
    s.add_argument("--train", choices=["A", "B"], required=True)
    s.add_argument("--feedback", choices=["gold", "self"], required=True)
    s.add_argument("--epochs", type=int, default=3); s.add_argument("--run", type=int, default=0)
    s.add_argument("--name"); s.add_argument("--limit", type=int); s.add_argument("--agent-url", default=DEFAULT_AGENT)
    s.add_argument("--dev-eval", action="store_true", help="바퀴마다 검증 문항 점수 기록 (채점자 API 추가 사용)")
    s = sub.add_parser("answer")
    s.add_argument("--test", choices=["A", "B"], required=True); s.add_argument("--run", required=True)
    s.add_argument("--playbook"); s.add_argument("--limit", type=int); s.add_argument("--workers", type=int, default=2)
    s.add_argument("--agent-url", default=DEFAULT_AGENT)
    s = sub.add_parser("online")
    s.add_argument("--test", choices=["A", "B"], required=True); s.add_argument("--run-name", required=True)
    s.add_argument("--run", type=int, default=0); s.add_argument("--limit", type=int); s.add_argument("--agent-url", default=DEFAULT_AGENT)
    s = sub.add_parser("audit"); s.add_argument("--playbook", required=True); s.add_argument("--test", choices=["A", "B"], required=True)
    s = sub.add_parser("compare")
    s.add_argument("--test", choices=["A", "B"], required=True); s.add_argument("--new", required=True)
    s.add_argument("--base", default="agent_gpt-5.6-terra")
    a = ap.parse_args()
    return {"split": cmd_split, "evolve": cmd_evolve, "answer": cmd_answer, "online": cmd_online,
            "audit": cmd_audit, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
