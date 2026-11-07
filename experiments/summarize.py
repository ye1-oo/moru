"""실험 B 결과를 표·그림·사례 비교로 정리한다. LLM 호출 없음.

출력
- results/exp_b_runs.csv: 실행(조건×주×반복)별 지표
- results/exp_b_summary.csv, results/tables.md: 실험별 표(표본 수, 실행 횟수 포함)
- results/exp_b_by_case.csv: 사례 유형(시점 모호, 캡션에만 있음, 서술-캡션 불일치, 유혹 문항 등)별 결과
- results/figures/*.png
- results/examples/cases.md: "같은 입력, 다른 구조·컨텍스트, 다른 출력" 사례(문항 원문 가림)
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru import config, context, evaluate, pipeline  # noqa: E402

RESULTS = config.RESULTS_DIR
EXPERIMENTS = {
    "① 단일 vs 멀티 에이전트": ["single", "multi"],
    "② 컨텍스트 요소별 제거": ["multi", "no_date", "no_source", "no_abstain", "none"],
    "③ 일기 / 캡션 / 둘 다": ["parent_only", "caption_only", "multi"],
    "④ 문항별 vs 일괄 검색": ["multi", "batched"],
}
CASE_KO = {"parent": "부모 서술", "caption_only": "캡션에만 있음", "conflict": "서술-캡션 불일치",
           "ambiguous_time": "시점 모호 표현", "both": "서술+캡션 일치", "bait": "유혹 문항(근거 없음)",
           "no_evidence": "근거 없음"}
METRICS = ["정확 일치", "±1 일치", "점수 재현율", "판단 보류 재현율", "판단 보류 정밀도", "환각 비율",
           "근거 추적 정확도", "출처 정확도", "검색 재현율"]


def run_table(results, gold) -> pd.DataFrame:
    rows = []
    for r in results:
        t = evaluate.item_table(r, gold)
        rows.append({"condition": r["condition"], "label": r["label"], "week": r["week"], "repeat": r["repeat"],
                     "items": len(t), **evaluate.metrics(t)})
    return pd.DataFrame(rows)


def summary_tables(results, gold) -> str:
    md = ["# 실험 B 결과", "",
          f"가상 아이 1명(생후 18개월), 2주(주당 일기 7편, 문항 48개), 모델 {config.GEMINI_MODEL}, temperature 0.",
          "값은 실행(주×반복)별 지표의 평균 ± 표준편차. '문항 판단 수' = 48 × 실행 수.", ""]
    all_rows = []
    for title, conds in EXPERIMENTS.items():
        subset = [r for r in results if r["condition"] in conds]
        if not subset:
            md += [f"## {title}", "", "(아직 실행하지 않음)", ""]
            continue
        table = evaluate.summarize(subset, gold)
        table["condition"] = pd.Categorical(table["condition"], conds, ordered=True)
        table = table.sort_values("condition")
        table.insert(0, "실험", title)
        all_rows.append(table)
        cols = ["조건", "주 수", "반복 수", "실행 수", "문항 판단 수"] + [m for m in METRICS if m in table.columns]
        md += [f"## {title}", "", table[cols].to_markdown(index=False), ""]
    if all_rows:
        pd.concat(all_rows).to_csv(RESULTS / "exp_b_summary.csv", index=False, encoding="utf-8-sig")
    return "\n".join(md)


def by_case(results, gold) -> pd.DataFrame:
    tables = pd.concat([evaluate.item_table(r, gold).assign(label=r["label"]) for r in results])
    rows = []
    for (label, case), g in tables.groupby(["label", "case"]):
        scored_gold = g[g["gold"].notna()]
        both = scored_gold[scored_gold["pred"].notna()]
        rows.append({"조건": label, "사례 유형": CASE_KO.get(case, case), "문항 판단 수": len(g),
                     "점수 부여 비율": round(g["pred"].notna().mean(), 2),
                     "정확 일치": round((both["gold"] == both["pred"]).mean(), 2) if len(both) else None,
                     "평균 confidence": round(g.loc[g["pred"].notna(), "confidence"].mean(), 2) if g["pred"].notna().any() else None})
    return pd.DataFrame(rows)


def figures(runs: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["AppleGothic"]
    plt.rcParams["axes.unicode_minus"] = False
    out = RESULTS / "figures"
    out.mkdir(parents=True, exist_ok=True)
    shown = ["정확 일치", "±1 일치", "환각 비율", "판단 보류 재현율", "근거 추적 정확도", "출처 정확도"]
    for title, conds in EXPERIMENTS.items():
        sub = runs[runs["condition"].isin(conds)]
        if sub["condition"].nunique() < 2:
            continue
        mean = sub.groupby("condition")[shown].mean().reindex([c for c in conds if c in set(sub["condition"])])
        std = sub.groupby("condition")[shown].std(ddof=0).reindex(mean.index).fillna(0)
        labels = [pipeline.CONDITIONS[c].label for c in mean.index]
        fig, ax = plt.subplots(figsize=(9, 4))
        width = 0.8 / len(mean)
        for i, (cond, row) in enumerate(mean.iterrows()):
            xs = [j + i * width for j in range(len(shown))]
            ax.bar(xs, row.values, width, yerr=std.loc[cond].values, label=labels[i], capsize=2)
        ax.set_xticks([j + width * (len(mean) - 1) / 2 for j in range(len(shown))], shown)
        ax.set_ylim(0, 1.05)
        n = sub.groupby("condition").size().min()
        ax.set_title(f"{title} (조건당 실행 {n}회 이상, 실행당 48문항)")
        ax.legend(fontsize=8, ncols=min(5, len(mean)))
        fig.tight_layout()
        fig.savefig(out / f"exp_b_{title[0]}.png", dpi=200)
        plt.close(fig)


# ---------------------------------------------------------------- 사례 비교
def item_fragment(prompt: str, item_id: str) -> str:
    """컨텍스트에서 그 문항이 속한 영역 블록(근거 기록 + 해당 문항 줄)만 잘라낸다."""
    lines = prompt.splitlines()
    item_line = next((i for i, l in enumerate(lines) if l.startswith(f"- {item_id}:")), None)
    if item_line is None:
        return ""
    start = max(i for i in range(item_line) if lines[i].startswith("## "))
    if "검색된 기록:" not in lines[item_line]:  # 단일 에이전트: 이번 주 기록 전체
        start = next(i for i, l in enumerate(lines) if l.startswith("## 이번 주 기록"))
        end = next(i for i, l in enumerate(lines) if l.startswith("## 문항"))
        return "\n".join(lines[start:end] + ["...", lines[item_line]])
    refs = lines[item_line].split("검색된 기록:")[1]
    wanted = {f"[기록 {x.strip().split()[-1].rstrip(')')}]" for x in refs.split(",") if x.strip() != "없음)"}
    block, keep = [], False
    for line in lines[start:item_line]:
        if line.startswith("[기록 "):
            keep = line.split("]")[0] + "]" in wanted
        elif line.startswith("###"):
            keep = False
        if keep:
            block.append(line)
    return "\n".join([lines[start]] + block + ["...", lines[item_line]])


def cases(results, gold, limit: int = 5) -> str:
    items = pipeline.load_items()
    by_key = {(r["condition"], r["week"]): r for r in results if r["repeat"] == 0}
    preferred = ["conflict", "caption_only", "ambiguous_time", "bait", "parent"]
    picks = []
    for case in preferred:
        for _, g in gold[gold["case"] == case].iterrows():
            outs = {}
            for cond in pipeline.CONDITIONS:
                r = by_key.get((cond, g["week"]))
                if r:
                    s = next(s for s in r["scores"] if s["item_id"] == g["item_id"])
                    outs[cond] = s
            distinct = {(o["score"], o["source"], o["evidence_date"]) for o in outs.values()}
            if len(outs) >= 2 and len(distinct) >= 2:
                picks.append((g, outs))
                break
        if len(picks) >= limit:
            break
    md = ["# 같은 입력, 다른 구조·컨텍스트, 다른 출력", "",
          "같은 주의 같은 일기·영상을 넣고, 에이전트 구조나 컨텍스트 요소만 바꿨을 때 한 문항의 출력이 어떻게 달라지는지 비교한다.",
          "K-DST 문항 원문은 저작권 때문에 〈문항 원문 비공개〉로 가렸다. 반복 0회차 결과.", ""]
    for n, (g, outs) in enumerate(picks, 1):
        gold_text = "판단 보류" if g["gold"] is None or pd.isna(g["gold"]) else f"{int(g['gold'])}점"
        md += [f"## 사례 {n}. {CASE_KO.get(g['case'], g['case'])}: {g['item_id']} ({g['week']}주차)", "",
               f"- 정답: {gold_text}. {g['note']}", ""]
        for cond, s in outs.items():
            r = by_key[(cond, g["week"])]
            fragment = context.mask_items(item_fragment(r["prompt"], g["item_id"]), items)
            output = {k: s[k] for k in ("score", "evidence_quote", "evidence_date", "source", "confidence")}
            md += [f"### {pipeline.CONDITIONS[cond].label}", "", "컨텍스트(해당 부분)", "", "```text", fragment, "```", "",
                   "출력", "", "```json", json.dumps(output, ensure_ascii=False, indent=1), "```", ""]
    return "\n".join(md)


def main() -> None:
    gold = evaluate.load_gold()
    results = evaluate.load_results(pipeline.RAW)
    if not results:
        print("결과 없음")
        return
    runs = run_table(results, gold)
    runs.to_csv(RESULTS / "exp_b_runs.csv", index=False, encoding="utf-8-sig")
    (RESULTS / "tables.md").write_text(summary_tables(results, gold), encoding="utf-8")
    by_case(results, gold).to_csv(RESULTS / "exp_b_by_case.csv", index=False, encoding="utf-8-sig")
    figures(runs)
    (RESULTS / "examples").mkdir(exist_ok=True)
    (RESULTS / "examples" / "cases.md").write_text(cases(results, gold), encoding="utf-8")
    print((RESULTS / "tables.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
