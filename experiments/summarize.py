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
# 첫 조건이 비교 기준이다. ④ 문항별 vs 일괄 검색은 2026-11-08 "향후 실험 계획"으로 돌렸다.
EXPERIMENTS = {
    "① 단일 vs 멀티 에이전트": ["multi", "single"],
    "② 컨텍스트 요소별 제거": ["multi", "no_date", "no_source", "no_abstain", "none"],
    "③ 일기 / 캡션 / 둘 다": ["multi", "parent_only", "caption_only"],
}
MAIN = ["환각 비율", "근거 추적 정확도"]          # 주 지표
AUX = ["정확 일치", "점수 재현율", "출처 정확도"]  # 보조 지표(±1 일치는 쓰지 않음)
NOTES = {
    "① 단일 vs 멀티 에이전트": [
        "단일 에이전트는 캡션 대신 원본 영상을 직접 봤다. 정답은 일기와 캡션 텍스트로 만들었으므로, 단일 에이전트가 영상에서 "
        "실제로 본 행동(캡션에 없는 행동)에 점수를 주면 환각으로 집계된다. 단일 에이전트의 환각 비율은 과대 추정일 수 있다.",
        "단일 에이전트가 영상 근거로 쓴 문장은 자기 말로 쓴 묘사라 실제 기록에서 찾을 수 없다. 근거 추적 정확도가 낮은 것은 "
        "점수가 틀렸다는 뜻이 아니라 근거를 기록으로 되짚을 수 없다는 뜻이다.",
    ],
    "② 컨텍스트 요소별 제거": [
        "출처 태그를 빼도 출처 정확도가 유지되는 것은 캡션의 문체(\"~합니다\")로 출처를 추정할 수 있었기 때문으로 보인다.",
        "판단 보류 규칙을 빼도 환각 비율이 늘지 않았다. '기록에 적힌 내용만 근거로 삼는다'는 기본 규칙과 null을 허용하는 "
        "출력 스키마가 남아 있기 때문으로 보인다. 이 데이터에서는 판단 보류 규칙 문장 자체의 효과를 확인하지 못했다.",
        "근거 추적 정확도는 날짜 태그가 없으면 크게 떨어진다. 모델이 근거 날짜를 평가 기간 첫날로 적거나 비워 두었다.",
    ],
    "③ 일기 / 캡션 / 둘 다": [
        "'일기만'은 점수 재현율이 낮다. 캡션에만 있는 행동(예: 컵으로 혼자 마시기, 숟가락 사용)을 근거로 쓸 수 없기 때문이다.",
        "'캡션만' 1주차는 텍스트 입력이 안전 필터(prohibited_content)에 막혀 재전송하지 않고 제외했다. 2주차 1회만 집계했다.",
    ],
}


def _cell(mean, std, runs):
    return f"{mean:.2f}" + (f" ± {std:.2f}" if runs > 1 else "")


def no_difference(ref: pd.DataFrame, cond: pd.DataFrame, metric: str) -> bool:
    """기준 조건과의 차이가 표본 대비 작은가.
    (1) 평균 차이가 실행당 문항 1개 미만에 해당하거나 (2) 실행이 2회 이상이고 차이가 두 조건 표준편차 중 큰 값 이하."""
    a, b = ref[metric].dropna(), cond[metric].dropna()
    if a.empty or b.empty:
        return False
    delta = abs(b.mean() - a.mean())
    per_run = pd.concat([ref[f"n:{metric}"], cond[f"n:{metric}"]]).mean()
    if delta * per_run < 1:
        return True
    return len(a) > 1 and len(b) > 1 and delta <= max(a.std(ddof=0), b.std(ddof=0))
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


def summary_tables(runs: pd.DataFrame) -> str:
    md = ["# 실험 B 결과", "",
          f"가상 아이 1명(생후 18개월), 2주(주당 가상 일기 7편, 18~19개월 검사지 48문항), 모델 {config.GEMINI_MODEL}, temperature 0.",
          "값은 실행(주×반복)별 지표의 평균 ± 표준편차. 문항 판단 수 = 48 × 실행 수.",
          "**주 지표: 환각 비율(낮을수록 좋음), 근거 추적 정확도(높을수록 좋음).** 정확 일치·점수 재현율·출처 정확도는 보조 지표.",
          "'(차이 없음)': 첫 행(기준)과의 평균 차이가 실행당 문항 1개 미만이거나, 반복이 있을 때 표준편차 이하인 경우.",
          "정답 라벨은 2026-11-08에 고정했다(이전 수정 1회: 첫 실행 후 fine_motor_05 누락 보완).", ""]
    rows = []
    for title, conds in EXPERIMENTS.items():
        present = [c for c in conds if c in set(runs["condition"])]
        md += [f"## {title}", ""]
        if len(present) < 2:
            md += ["(아직 실행하지 않음)", ""]
            continue
        ref = runs[runs["condition"] == present[0]]
        table = []
        for cond in present:
            sub = runs[runs["condition"] == cond]
            row = {"조건": pipeline.CONDITIONS[cond].label, "주 수": sub["week"].nunique(),
                   "반복 수": sub["repeat"].nunique(), "실행 수": len(sub), "문항 판단 수": int(sub["items"].sum())}
            for metric in MAIN + AUX:
                value = _cell(sub[metric].mean(), sub[metric].std(ddof=0), len(sub))
                if cond == present[0]:
                    value += " (기준)" if metric in MAIN else ""
                elif no_difference(ref, sub, metric):
                    value += " (차이 없음)"
                row[("주 · " if metric in MAIN else "보조 · ") + metric] = value
            table.append(row)
            rows.append({"실험": title, "condition": cond, **row})
        md += [pd.DataFrame(table).to_markdown(index=False), ""]
        md += [f"- {note}" for note in NOTES.get(title, [])] + [""]
    md += ["## 향후 실험 계획", "",
           "- ④ 문항별 검색 vs 일괄 검색: 주당 기록이 7편이라 top-3 검색이 대부분의 기록을 가져와 차이가 드러나기 어렵고, "
           "무료 호출 한도를 ①② 반복에 쓰기 위해 이번에는 하지 않았다(2026-11-08). 기록이 많은 장기 데이터에서 비교할 계획이다.", ""]
    pd.DataFrame(rows).to_csv(RESULTS / "exp_b_summary.csv", index=False, encoding="utf-8-sig")
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
    shown = MAIN + ["정확 일치"]
    for number, (title, conds) in enumerate(EXPERIMENTS.items(), 1):
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
        ax.set_title(f"{title} (조건당 실행 {n}회 이상, 실행당 48문항. 환각 비율은 낮을수록 좋음)")
        ax.legend(fontsize=8, ncols=min(5, len(mean)))
        fig.tight_layout()
        fig.savefig(out / f"exp_b_{number}.png", dpi=200)
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
    # 사례 유형마다 조건 간 출력(점수, 출처, 날짜)이 가장 많이 갈린 문항을 하나씩 고른다.
    preferred = ["conflict", "ambiguous_time", "caption_only", "bait", "parent"]
    picks = []
    for case in preferred:
        best = None
        for _, g in gold[gold["case"] == case].iterrows():
            outs = {}
            for cond in pipeline.CONDITIONS:
                r = by_key.get((cond, g["week"]))
                if r:
                    outs[cond] = next(s for s in r["scores"] if s["item_id"] == g["item_id"])
            distinct = len({(o["score"], o["source"], o["evidence_date"]) for o in outs.values()})
            if len(outs) >= 2 and distinct >= 2 and (best is None or distinct > best[0]):
                best = (distinct, g, outs)
        if best:
            picks.append(best[1:])
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
    (RESULTS / "tables.md").write_text(summary_tables(runs), encoding="utf-8")
    by_case(results, gold).to_csv(RESULTS / "exp_b_by_case.csv", index=False, encoding="utf-8-sig")
    figures(runs)
    (RESULTS / "examples").mkdir(exist_ok=True)
    (RESULTS / "examples" / "cases.md").write_text(cases(results, gold), encoding="utf-8")
    print((RESULTS / "tables.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
