#!/usr/bin/env python3
"""결과 그래프 PNG (API 없음, 저장된 채점 결과만, 2026-11-17).

필요: matplotlib (예: pip install matplotlib). 글꼴은 macOS의 Apple SD Gothic Neo.
결과: output/결과그래프/*.png
  01_정확도_유형별.png       네 유형 × 세 모델, 기본 AI vs RAG 추가
  02_정확도_네유형평균.png   모델별 네 유형 평균 + 세 모델 평균
  03_틀린이유.png            RAG 추가 후 틀린 문항(374 중): 페이지를 못 찾음 vs 페이지 있는데 틀림
  04_안전오답.png            '높음 · 안전' 오답 문항 수(C·D), 기본 AI vs RAG 추가
색: 기본 AI #C9772B, RAG 추가 #1C64B8 / 페이지 못 찾음 #7B5EA7, 페이지 있는데 틀림 #14917F
    (dataviz validate_palette.js 라이트 모드 통과)
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_models as CM  # noqa: E402
import risk_analysis as R  # noqa: E402

OUTD = HERE / "output" / "결과그래프"
MODELS = [("gpt-5.6-terra", "gpt-5.6-terra"), ("claude-opus-5-5", "Claude Opus 5.5"), ("qwen3-14b-bf16", "Qwen3-14B")]
SHORT = {"gpt-5.6-terra": "gpt", "claude-opus-5-5": "Opus", "qwen3-14b-bf16": "Qwen"}
TYPES = [("A 급여 기준 (101)", "", "a_items.jsonl", "llm", True), ("A2 추가 규칙 (38)", "a2_", "a2_items.jsonl", "llm", False),
         ("C 환자 판정 (198)", "c_", "c_items.jsonl", "code", False), ("D 약 고르기 (37)", "d_", "d_items.jsonl", "code", False)]
BASE, RAG = "#C9772B", "#1C64B8"
RET, READ = "#7B5EA7", "#14917F"
INK, MUTED, GRID = "#1F2A33", "#5F6B76", "#E3E7EA"


def setup_font():
    for f in ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf"):
        if Path(f).exists():
            font_manager.fontManager.addfont(f)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name()
            break
    plt.rcParams.update({"axes.unicode_minus": False, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK, "figure.dpi": 100})


def score(prefix, items, kind, main, model, arm):
    s = CM.llm_scores(prefix, items, model, arm, main)[0] if kind == "llm" else CM.code_scores(prefix, model, arm)
    return sum(s.values()) / len(s)


def clean(ax):
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def bars(ax, labels, base, rag, ymax=1.0, fmt="{:.2f}"):
    import numpy as np
    x = np.arange(len(labels)); w = 0.36
    b1 = ax.bar(x - w / 2 - 0.01, base, w, color=BASE, label="기본 AI")
    b2 = ax.bar(x + w / 2 + 0.01, rag, w, color=RAG, label="RAG 추가")
    for bs in (b1, b2):
        for b in bs:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + ymax * 0.015, fmt.format(b.get_height()),
                    ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, ymax * 1.12)
    clean(ax)


def main() -> int:
    setup_font()
    OUTD.mkdir(parents=True, exist_ok=True)
    data = {}
    for m, _ in MODELS:
        for t in TYPES:
            for arm in ("llm", "agent"):
                data[(m, t[0], arm)] = score(t[1], t[2], t[3], t[4], m, arm)

    # 01 유형별
    fig, axes = plt.subplots(1, 4, figsize=(16, 5), sharey=True)
    for ax, t in zip(axes, TYPES):
        bars(ax, [SHORT[m] for m, _ in MODELS], [data[(m, t[0], "llm")] for m, _ in MODELS], [data[(m, t[0], "agent")] for m, _ in MODELS])
        ax.set_title(t[0], fontsize=13, color=INK, pad=10)
    axes[0].set_ylabel("점수 (1.0 = 만점)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncol=2, frameon=False, fontsize=11)
    fig.suptitle("유형별 정확도: 세 모델 모두 RAG를 추가하면 올랐다", x=0.01, ha="left", fontsize=16, fontweight="bold")
    fig.text(0.01, 0.005, "A·A2: AI 채점자(gpt-6-sol) 맞음 1·부분 0.5 평균 / C: 정답률 / D: 완전 일치율. 답 1회·채점 1회, 임상의 검증 전.", fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93)); fig.savefig(OUTD / "01_정확도_유형별.png", dpi=150); plt.close(fig)

    # 02 네 유형 평균
    avg = {(m, arm): sum(data[(m, t[0], arm)] for t in TYPES) / 4 for m, _ in MODELS for arm in ("llm", "agent")}
    labs = [n for _, n in MODELS] + ["세 모델 평균"]
    b = [avg[(m, "llm")] for m, _ in MODELS]; r = [avg[(m, "agent")] for m, _ in MODELS]
    b.append(sum(b) / 3); r.append(sum(r) / 3)
    fig, ax = plt.subplots(figsize=(10, 5.6))
    bars(ax, labs, b, r)
    ax.axvline(2.5, color=GRID, linewidth=1.2)
    ax.set_ylabel("네 유형(A·A2·C·D) 평균 점수")
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=11)
    ax.set_title("네 유형 평균: 기본 AI 0.36 → RAG 추가 0.74 (세 모델 평균)", loc="left", fontsize=15, fontweight="bold", pad=14)
    fig.text(0.01, 0.01, "모델마다 네 유형 점수를 같은 비중으로 평균. 세 모델 평균은 그 세 값의 평균.", fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUTD / "02_정확도_네유형평균.png", dpi=150); plt.close(fig)

    # 03 틀린 이유 (오답원인_모델별.json: error_analysis_models.py 결과)
    E = json.loads((HERE / "eval_out" / "오답원인_모델별.json").read_text(encoding="utf-8"))
    ret, other = [], []
    for m, _ in MODELS:
        k = f"{SHORT[m]} 에이전트"; t_ = r_ = 0
        for T in ("A", "A2"):
            t_ += len(E[T][k]); r_ += sum(1 for x in E[T][k] if x["원인"].startswith("검색"))
        t_ += len(E["C"][k]); r_ += sum(1 for x in E["C"][k] if x.get("핵심 쪽 검색") is False)
        for x in E["D"][k]["문항"]:
            t_ += 1
            ev = [e.split(":")[0] for e in x["사건"]]
            r_ += bool(ev) and all("쪽 없음" in e for e in ev)
        ret.append(r_); other.append(t_ - r_)
    fig, ax = plt.subplots(figsize=(11, 5.0))
    names = [n for _, n in MODELS][::-1]; ret_r, oth_r = ret[::-1], other[::-1]
    ax.barh(names, ret_r, color=RET, height=0.55, label="페이지를 못 찾음 (검색)")
    ax.barh(names, oth_r, left=ret_r, color=READ, height=0.55, label="페이지가 있는데 틀림 (읽기·답변)", edgecolor="white", linewidth=2)
    for i, (a, o) in enumerate(zip(ret_r, oth_r)):
        ax.text(a / 2, i, str(a), ha="center", va="center", color="white", fontsize=12, fontweight="bold")
        if o >= 3:
            ax.text(a + o / 2, i, str(o), ha="center", va="center", color="white", fontsize=12, fontweight="bold")
        ax.text(a + o + 1.5, i, f"틀린 문항 {a + o} / 374", va="center", fontsize=11, color=INK)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.xaxis.grid(True, color=GRID); ax.set_axisbelow(True); ax.set_xlim(0, max(r + o for r, o in zip(ret, other)) * 1.3)
    ax.set_xlabel("RAG 추가 후 틀린 문항 수 (네 유형 374문항, 부분 점수 포함)")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=11, ncol=2)
    ax.set_title("틀린 이유: 페이지를 못 찾은 문항은 세 모델이 비슷하고, 차이는 읽기에서 났다", loc="left", fontsize=14, fontweight="bold", pad=34)
    fig.text(0.01, 0.01, "코드 규칙 분류(error_analysis_models.py). Opus의 '읽기' 2문항은 정답 해석 문제(소아 평가 시점, 임상의 확인 필요).", fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(OUTD / "03_틀린이유.png", dpi=150); plt.close(fig)

    # 04 안전 오답
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, (T, title) in zip(axes, (("C", "C 환자 판정"), ("D", "D 약 고르기"))):
        bv, rv = [], []
        for m, _ in MODELS:
            for arm, side, lst in (("llm", "기본 AI", bv), ("agent", "에이전트", rv)):
                rows = R.c_rows(side, f"{arm}_{m}") if T == "C" else R.d_rows(side, f"{arm}_{m}")
                lst.append(sum(1 for x in rows if x["위험도"] == R.LEVELS[0]))
        bars(ax, [SHORT[m] for m, _ in MODELS], bv, rv, ymax=8, fmt="{:.0f}")
        ax.set_title(title, fontsize=13, pad=10)
    axes[0].set_ylabel("‘높음 · 안전’ 오답 문항 수")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncol=2, frameon=False, fontsize=11)
    fig.suptitle("위험한 오답: D형 6문항은 RAG를 추가한 세 모델이 똑같이 틀렸다", x=0.01, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.01, 0.005, "검사 수치 미달·고령 등 안전 조건에 걸린 환자에게 약을 허용한 오답(risk_analysis.py 규칙). 원인: 체크리스트 쪽(p.49·52)이 검색된 5쪽에 없음.", fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 0.92)); fig.savefig(OUTD / "04_안전오답.png", dpi=150); plt.close(fig)
    print("저장:", OUTD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
