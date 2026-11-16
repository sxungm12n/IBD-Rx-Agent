"""v1(+교정) vs v2 채점 비교. 사용: python3 compare_v2.py <STAGE1 dir> [v2|v21]"""
import csv, json, sys, collections, random, math
from pathlib import Path

ST = Path(sys.argv[1]); EO = ST / "eval_out"; TAG = sys.argv[2] if len(sys.argv) > 2 else "v2"
S = {"맞음": 1.0, "부분": 0.5, "틀림": 0.0}
items = {json.loads(l)["id"]: json.loads(l) for l in (ST / "output/a_items.jsonl").read_text().splitlines() if l.strip()}
main_ids = [i for i, it in items.items() if not it["기준"].startswith("금기")]


def load(p):
    return {json.loads(l)["id"]: json.loads(l)["최종"] for l in p.read_text().splitlines() if l.strip()} if p.exists() else {}


def overrides(run):
    p = EO / run / "claude_review_NOT_human.csv"
    with p.open(encoding="utf-8-sig") as f:
        return {r["id"]: r["사람 판정"] for r in csv.DictReader(f)}


def kappa(a, b):
    ids = [i for i in a if i in b]; n = len(ids)
    po = sum(a[i] == b[i] for i in ids) / n
    ca, cb = collections.Counter(a[i] for i in ids), collections.Counter(b[i] for i in ids)
    pe = sum(ca[k] * cb[k] for k in S) / n / n
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def score(lbl, ids):
    return sum(S[lbl[i]] for i in ids) / len(ids)


def majority(reps):
    out = {}
    for i in reps[0]:
        vals = [r[i] for r in reps if i in r]
        c = collections.Counter(vals).most_common()
        out[i] = c[0][0] if c[0][1] > len(vals) / 2 else sorted(vals, key=lambda v: S[v])[len(vals) // 2]  # 동률이면 중앙값
    return out


res = {}
for run in ["llm_gpt-5.6-terra", "agent_gpt-5.6-terra"]:
    v1 = load(EO / run / "graded.jsonl"); ov = overrides(run)
    v1c = {**v1, **ov}
    reps = [load(EO / run / n) for n in [f"graded_{TAG}.jsonl", f"graded_{TAG}_r1.jsonl", f"graded_{TAG}_r2.jsonl"]]
    reps = [r for r in reps if len(r) >= len(items)]
    maj = majority(reps)
    print(f"\n=== {run}  ({TAG} 반복 {len(reps)}회)")
    print(f"v1 원래 점수        {score(v1, main_ids):.3f}")
    print(f"v1 + Claude 검토({len(ov)}건)    {score(v1c, main_ids):.3f}")
    for k, r in enumerate(reps):
        print(f"{TAG} #{k}               {score(r, main_ids):.3f}")
    print(f"{TAG} 다수결           {score(maj, main_ids):.3f}  분포 {dict(collections.Counter(maj[i] for i in main_ids))}")
    sm = {i: maj[i] for i in main_ids}
    po, k = kappa(sm, {i: v1c[i] for i in main_ids}); print(f"v2 다수결 vs v1+Claude검토: 일치 {po:.3f}, kappa {k:.3f}")
    po, k = kappa(sm, {i: v1[i] for i in main_ids}); print(f"v2 다수결 vs v1 원래: 일치 {po:.3f}, kappa {k:.3f}")
    # 교정 문항에서 v2가 교정 판정과 같은지
    hit = [i for i in ov if maj.get(i) == ov[i]]
    print(f"Claude 검토 {len(ov)}건 중 v2가 교정 판정과 같음: {len(hit)}  / 다른 것: {[ (i, ov[i], maj.get(i)) for i in ov if i not in hit]}")
    if len(reps) >= 2:
        all_same = sum(len({r[i] for r in reps}) == 1 for i in main_ids) / len(main_ids)
        pk = [kappa({i: reps[a][i] for i in main_ids}, {i: reps[b][i] for i in main_ids})[1]
              for a in range(len(reps)) for b in range(a + 1, len(reps))]
        print(f"{TAG} 자체 일관성: 반복 모두 같은 판정 {all_same:.3f}, 쌍별 kappa 평균 {sum(pk)/len(pk):.3f}")
    # v1+교정과 다른 문항
    diff = [(i, v1c[i], maj[i]) for i in main_ids if v1c[i] != maj[i]]
    print(f"v1+Claude검토와 판정이 다른 문항 {len(diff)}건:")
    for d in diff:
        print("  ", *d)
    res[run] = maj

# 짝 비교 ({TAG} 다수결)
b, a = res["llm_gpt-5.6-terra"], res["agent_gpt-5.6-terra"]
up = sum(S[a[i]] > S[b[i]] for i in main_ids); dn = sum(S[a[i]] < S[b[i]] for i in main_ids)
n = up + dn; p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(up, dn) + 1)) / 2 ** n) if n else 1
diffs = [S[a[i]] - S[b[i]] for i in main_ids]; random.seed(0)
bs = sorted(sum(random.choice(diffs) for _ in diffs) / len(diffs) for _ in range(10000))
print(f"\n에이전트 - 베이스라인 ({TAG} 다수결): {sum(diffs)/len(diffs):+.3f}, 95% CI [{bs[250]:+.3f}, {bs[9749]:+.3f}], 개선 {up} / 악화 {dn}, sign test p={p:.2g}")
