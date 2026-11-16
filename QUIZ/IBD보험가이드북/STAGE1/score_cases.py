#!/usr/bin/env python3
"""C형(환자 판정)·D형(약제 선택) 답을 코드로 채점한다. OpenAI API를 쓰지 않는다 (2026-11-12).

C형: 답의 "판정: 예/아니오/판단 불가"를 정답 판정과 비교 → 맞음 / 틀림. 판정 줄을 못 읽으면 '형식 오류'(틀림).
D형(보기 없음): '인정:' 줄의 약 집합을 정답 집합과 비교. 완전 일치 → 맞음. 가이드북에 없는 약(해외 허가 약 등),
     이미 실패한 약, 생물학제제·소분자제제가 아닌 약, 알아보지 못한 이름을 따로 센다.
(보기를 주는 예전 D형 채점: 후보 9종마다 인정/제외 분류를 정답과 비교. 형식 '약제 집합'인 문항에만 쓴다)
     - 약별 정답률 = 맞게 분류한 후보 수 / 후보 수 (답에 없거나 인정·제외 양쪽에 쓴 약은 틀림)
     - 완전 일치 = 후보 전부 맞음 → 최종 '맞음', 하나라도 틀리면 '틀림'
     - 제외 이유는 여기서 채점하지 않는다 (필요하면 따로 채점자로)
사용 (IBD보험가이드북 폴더에서):
  python3 STAGE1/score_cases.py --run c_llm_gpt-5.6-terra --items STAGE1/output/c_items.jsonl
  python3 STAGE1/score_cases.py --run d_agent --items STAGE1/output/d_items.jsonl
결과: eval_out/<run>/graded_code.jsonl, summary_code.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_ROOT = HERE / "eval_out"

VERDICT = re.compile(r"판정\s*\**\s*[:：]\s*\**\s*(예|아니오|아니요|판단\s*불가)")
LEADING = re.compile(r"^\s*\**\s*(예|아니오|아니요|판단\s*불가)\b")

# 성분명·한글명·대표 상품명 → 성분명
DRUG_ALIASES = {
    "Infliximab": ["infliximab", "인플릭시맙", "인플릭시맵", "인플릭시마브", "레미케이드", "remicade", "램시마", "remsima", "레마로체"],
    "Adalimumab": ["adalimumab", "아달리무맙", "아달리무맵", "아달리무마브", "휴미라", "humira", "유플라이마", "아달로체"],
    "Golimumab": ["golimumab", "골리무맙", "골리무맵", "심퍼니", "simponi"],
    "Vedolizumab": ["vedolizumab", "베돌리주맙", "베도리주맙", "베돌리주맵", "킨텔레스", "kynteles", "entyvio", "엔티비오"],
    "Ustekinumab": ["ustekinumab", "우스테키누맙", "우스테키누맵", "스텔라라", "stelara"],
    "Tofacitinib": ["tofacitinib", "토파시티닙", "토파시티니브", "젤잔즈", "xeljanz"],
    "Filgotinib": ["filgotinib", "필고티닙", "필고티니브", "지셀레카", "jyseleca"],
    "Upadacitinib": ["upadacitinib", "우파다시티닙", "유파다시티닙", "우파다시티니브", "린버크", "rinvoq"],
    "Ozanimod": ["ozanimod", "오자니모드", "오자니모", "제포시아", "zeposia"],
}


# 2024 가이드북에 없는 생물학제제·소분자제제 (해외 허가 약 등). 한국 급여 여부는 따로 확인할 것
FOREIGN_ALIASES = {
    "Risankizumab": ["risankizumab", "리산키주맙", "스카이리치", "skyrizi"],
    "Mirikizumab": ["mirikizumab", "미리키주맙", "옴보", "omvoh"],
    "Guselkumab": ["guselkumab", "구셀쿠맙", "트렘피어", "tremfya"],
    "Etrasimod": ["etrasimod", "에트라시모드", "벨시피티", "velsipity"],
    "Certolizumab": ["certolizumab", "세르톨리주맙", "심지아", "cimzia"],
    "Natalizumab": ["natalizumab", "나탈리주맙", "티사브리", "tysabri"],
}
# 생물학제제·소분자제제가 아닌 약 (질문 범위 밖)
CONVENTIONAL_ALIASES = {
    "Azathioprine": ["azathioprine", "아자티오프린"], "Mercaptopurine": ["mercaptopurine", "6-mp", "머캅토퓨린"],
    "Methotrexate": ["methotrexate", "메토트렉세이트"], "Cyclosporine": ["cyclosporin", "사이클로스포린", "시클로스포린"],
    "Tacrolimus": ["tacrolimus", "타크롤리무스"], "5-ASA": ["mesalamine", "mesalazine", "메살라진", "5-asa", "sulfasalazine", "설파살라진"],
    "Corticosteroid": ["steroid", "스테로이드", "prednisolone", "프레드니솔론", "budesonide", "부데소니드"],
}


def load_jsonl(path: Path) -> dict:
    if not path.exists():
        return {}
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["id"]: r for r in rows}


def drugs_in(text: str) -> list[str]:
    low = text.lower()
    return [name for name, aliases in DRUG_ALIASES.items() if any(a in low for a in aliases)]


def parse_c(reply: str) -> str | None:
    m = VERDICT.search(reply) or LEADING.search(reply)
    if not m:
        return None
    v = re.sub(r"\s+", " ", m.group(1))
    return "아니오" if v == "아니요" else v


def parse_d(reply: str) -> dict[str, set[str]]:
    """{'인정': {...}, '제외': {...}}. '제외: 약 - 이유'는 이유 부분의 약 이름을 세지 않도록 구분자 앞만 본다."""
    out = {"인정": set(), "제외": set()}
    for line in reply.splitlines():
        m = re.match(r"^\s*[-*•]?\s*\**\s*(인정|제외)\s*\**\s*[:：]\s*(.*)$", line)
        if not m:
            continue
        kind, rest = m.group(1), m.group(2)
        if kind == "제외":
            rest = re.split(r"\s[-–—:]\s|\s?[-–—]\s|\(|:", rest, maxsplit=1)[0]
        if kind == "인정" and re.fullmatch(r"\s*(없음|없다|해당\s*없음)\.?\s*", rest):
            continue
        out[kind] |= set(drugs_in(rest))
    return out


def parse_d2(reply: str) -> tuple[set[str], set[str], set[str], list[str], bool]:
    """'인정:' 줄(없으면 첫 줄)에서 (가이드북 약, 해외 약, 범위 밖 약, 알아보지 못한 이름, 형식 오류)."""
    line, bad = None, False
    for ln in reply.splitlines():
        m = re.match(r"^\s*[-*•]?\s*\**\s*인정\s*\**\s*[:：]\s*(.*)$", ln)
        if m:
            line = m.group(1)
            break
    if line is None:
        bad, line = True, (reply.strip().splitlines() or [""])[0]
    if re.fullmatch(r"\s*(없음|없다|해당\s*없음)\.?\s*", line):
        return set(), set(), set(), [], bad
    guide, foreign, conv, unknown = set(), set(), set(), []
    for seg in re.split(r"[,，、/]|\s및\s|\s또는\s", line):
        seg = seg.strip(" .")
        if not seg:
            continue
        low = seg.lower()
        hit = False
        for table, out in ((DRUG_ALIASES, guide), (FOREIGN_ALIASES, foreign), (CONVENTIONAL_ALIASES, conv)):
            for name, aliases in table.items():
                if any(a in low for a in aliases):
                    out.add(name)
                    hit = True
        if not hit:
            unknown.append(seg)
    return guide, foreign, conv, unknown, bad


def score_d2(item: dict, reply: str) -> dict:
    key = item["answer"]["채점"]
    gold = set(key["인정"])
    guide, foreign, conv, unknown, bad = parse_d2(reply)
    said = guide | foreign | conv
    tp = len(guide & gold)
    failed = key.get("이미 실패한 약")
    exact = guide == gold and not foreign and not conv and not unknown
    return {"인정(답)": sorted(said), "인정(정답)": sorted(gold), "가이드북 약 중 틀리게 넣음": sorted(guide - gold),
            "빠뜨림": sorted(gold - guide), "해외·가이드북 밖 약": sorted(foreign), "범위 밖 약": sorted(conv),
            "알아보지 못한 이름": unknown, "이미 실패한 약 다시 씀": bool(failed and failed in guide),
            "정밀도": round(tp / len(said), 4) if said else None, "재현율": round(tp / len(gold), 4) if gold else None,
            "형식 오류": bad, "최종": "맞음" if exact else "틀림"}


def score_c(item: dict, reply: str) -> dict:
    gold = item["answer"]["채점"]["판정"]
    got = parse_c(reply)
    return {"판정(답)": got, "판정(정답)": gold, "형식 오류": got is None,
            "최종": "맞음" if got == gold else "틀림"}


def score_d(item: dict, reply: str) -> dict:
    key = item["answer"]["채점"]
    ok, ng = set(key["인정"]), set(key["제외"])
    cands = sorted(ok | ng)
    got = parse_d(reply)
    per = {}
    for d in cands:
        a, b = d in got["인정"], d in got["제외"]
        said = "인정" if a and not b else ("제외" if b and not a else ("양쪽" if a and b else "없음"))
        per[d] = {"답": said, "정답": "인정" if d in ok else "제외", "맞음": said == ("인정" if d in ok else "제외")}
    n_ok = sum(v["맞음"] for v in per.values())
    tp = len(got["인정"] & ok)
    return {"약별": per, "약별 정답 수": n_ok, "후보 수": len(cands), "약별 정답률": round(n_ok / len(cands), 4),
            "인정 정밀도": round(tp / len(got["인정"]), 4) if got["인정"] else None,
            "인정 재현율": round(tp / len(ok), 4) if ok else None,
            "형식 오류": not (got["인정"] or got["제외"]) and "인정" not in reply,
            "최종": "맞음" if n_ok == len(cands) else "틀림"}


def summarize(items: list[dict], graded: dict) -> dict:
    done = [i for i in items if i["id"] in graded]
    if not done:
        return {"문항": len(items), "채점됨": 0}
    kind = done[0]["type"]
    acc = lambda group: round(sum(graded[i["id"]]["최종"] == "맞음" for i in group) / len(group), 4) if group else None
    summ = {"유형": kind, "문항": len(items), "채점됨": len(done), "정답률(완전 일치)": acc(done),
            "형식 오류": sum(graded[i["id"]].get("형식 오류", False) for i in done)}
    by = collections.defaultdict(list)
    for i in done:
        by[i["gate"] if kind == "C" else i["기준"]].append(i)
    summ["기준별"] = {k: {"문항": len(v), "정답률": acc(v)} for k, v in by.items()}
    if kind == "C":
        summ["기준 평균(기준마다 같은 비중)"] = round(sum(acc(v) for v in by.values()) / len(by), 4)
        by_gold = collections.defaultdict(list)
        for i in done:
            by_gold[i["answer"]["채점"]["판정"]].append(i)
        summ["정답 판정별"] = {k: {"문항": len(v), "정답률": acc(v)} for k, v in by_gold.items()}
        summ["함정 문항 정답률"] = acc([i for i in done if i["answer"]["채점"].get("함정")])
    elif done[0]["answer"]["형식"] == "약제 집합":
        summ["약별 정답률 평균"] = round(sum(graded[i["id"]]["약별 정답률"] for i in done) / len(done), 4)
        summ["함정 사례 완전 일치"] = acc([i for i in done if i["answer"]["채점"].get("함정")])
    else:  # 보기 없는 D형
        g = [graded[i["id"]] for i in done]
        rec = [r["재현율"] for r in g if r["재현율"] is not None]
        pre = [r["정밀도"] for r in g if r["정밀도"] is not None]
        summ["재현율 평균(정답 약이 있는 사례)"] = round(sum(rec) / len(rec), 4) if rec else None
        summ["정밀도 평균(약을 쓴 사례)"] = round(sum(pre) / len(pre), 4) if pre else None
        summ["해외·가이드북 밖 약을 쓴 사례"] = sum(bool(r["해외·가이드북 밖 약"]) for r in g)
        summ["해외·가이드북 밖 약별 횟수"] = dict(collections.Counter(d for r in g for d in r["해외·가이드북 밖 약"]))
        summ["범위 밖 약(전통 치료제)을 쓴 사례"] = sum(bool(r["범위 밖 약"]) for r in g)
        summ["이미 실패한 약을 다시 쓴 사례"] = sum(r["이미 실패한 약 다시 씀"] for r in g)
        summ["알아보지 못한 이름"] = [n for r in g for n in r["알아보지 못한 이름"]]
        summ["가이드북 약을 틀리게 넣은 횟수"] = dict(collections.Counter(d for r in g for d in r["가이드북 약 중 틀리게 넣음"]))
        summ["빠뜨린 횟수"] = dict(collections.Counter(d for r in g for d in r["빠뜨림"]))
        summ["함정 사례 완전 일치"] = acc([i for i in done if i["answer"]["채점"].get("함정")])
    return summ


def main() -> int:
    ap = argparse.ArgumentParser(description="C·D형 코드 채점 (API 없음)")
    ap.add_argument("--run", required=True, help="eval_out 아래 결과 폴더 이름")
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--answers", type=Path, help="답 파일 (기본: eval_out/<run>/answers.jsonl)")
    a = ap.parse_args()
    items = list(load_jsonl(a.items).values())
    kinds = {i["type"] for i in items}
    if not kinds <= {"C", "D"} or len(kinds) != 1:
        print(f"C형 또는 D형 한 가지만: {kinds}", file=sys.stderr)
        return 1
    out = OUT_ROOT / a.run
    answers = load_jsonl(a.answers or out / "answers.jsonl")
    stale = [i["id"] for i in items if i["id"] in answers and answers[i["id"]].get("질문") not in (None, i["question"])]
    if stale:
        print(f"질문이 바뀐 뒤의 답이 아닌 문항 {len(stale)}개는 채점하지 않음: {stale[:5]}")
    graded = {}
    for it in items:
        row = answers.get(it["id"])
        if not row or it["id"] in stale:
            continue
        reply = row["reply"].strip()
        rec = score_c(it, reply) if it["type"] == "C" else (score_d(it, reply) if it["answer"]["형식"] == "약제 집합" else score_d2(it, reply))
        graded[it["id"]] = {"id": it["id"], "채점 대상": reply, "채점": "코드", **rec}
    out.mkdir(parents=True, exist_ok=True)
    (out / "graded_code.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in graded.values()),
                                           encoding="utf-8")
    summ = summarize(items, graded)
    (out / "summary_code.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
