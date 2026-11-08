"""실험 B 지표.

문항 단위(한 주 48문항)로 정답과 비교한다.
- 정확 일치 / ±1 일치: 정답 점수가 있고 모델도 점수를 준 문항 기준
- 판단 보류 재현율: 정답이 판단 보류인 문항을 보류로 맞춘 비율. 정밀도: 모델이 보류한 문항 중 정답도 보류인 비율
- 환각 비율: 정답이 판단 보류인 문항 중 점수를 매긴 비율 (= 1 - 판단 보류 재현율)
- 점수 재현율: 정답 점수가 있는 문항 중 모델이 점수를 준 비율(과도한 보류 확인용)
- 근거 추적 정확도: 모델이 점수를 준 문항 중 근거 문장이 실제 일기·캡션에 있고 날짜도 그 기록과 같은 비율
- 출처 정확도: 근거 문장이 확인된 문항 중 출처(parent/caption)가 맞는 비율
- 검색 재현율: 정답 근거 일기가 문항의 top-k 검색 결과에 든 비율
"""

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

from moru import config

GOLD_WEEKLY = config.GOLD_DIR / "child_A_weekly.csv"


def load_gold() -> pd.DataFrame:
    gold = pd.read_csv(GOLD_WEEKLY, dtype=str, keep_default_na=False)
    gold["week"] = gold["week"].astype(int)
    gold["gold"] = gold["gold_score_or_abstain"].map(lambda v: None if v == "abstain" else int(v))
    return gold


def item_table(result: dict, gold: pd.DataFrame) -> pd.DataFrame:
    g = gold[gold["week"] == result["week"]].set_index("item_id")
    rows = []
    for s in result["scores"]:
        if s["item_id"] not in g.index:
            continue
        gi = g.loc[s["item_id"]]
        f = s["flags"]
        evidence = set(result.get("evidence", {}).get(s["item_id"], []))
        gold_diaries = [d for d in gi["evidence_diaries"].split(";") if d]
        rows.append({
            "condition": result["condition"], "week": result["week"], "repeat": result["repeat"],
            "item_id": s["item_id"], "case": gi["case"], "gold": gi["gold"], "pred": s["score"],
            "confidence": s["confidence"], "source": s["source"], "evidence_date": s["evidence_date"],
            "evidence_quote": s["evidence_quote"],
            "quote_found": f["quote_found"], "date_match": f["date_match"], "source_match": f["source_match"],
            "inconsistent": f["inconsistent"],
            "retrieved_gold": (sum(d in evidence for d in gold_diaries), len(gold_diaries)) if evidence else None,
        })
    return pd.DataFrame(rows)


def _ratio(num, den):
    return float(num) / den if den else np.nan


def metrics(table: pd.DataFrame) -> dict:
    gold_scored = table[table["gold"].notna()]
    gold_abstain = table[table["gold"].isna()]
    both = gold_scored[gold_scored["pred"].notna()]
    pred_abstain = table[table["pred"].isna()]
    pred_scored = table[table["pred"].notna()]
    traced = pred_scored["quote_found"].fillna(False).astype(bool) & pred_scored["date_match"].fillna(False).astype(bool)
    found = pred_scored[pred_scored["quote_found"].fillna(False).astype(bool)]
    out = {
        "정확 일치": _ratio((both["gold"] == both["pred"]).sum(), len(both)),
        "±1 일치": _ratio(((both["gold"] - both["pred"]).abs() <= 1).sum(), len(both)),
        "점수 재현율": _ratio(len(both), len(gold_scored)),
        "판단 보류 재현율": _ratio(gold_abstain["pred"].isna().sum(), len(gold_abstain)),
        "판단 보류 정밀도": _ratio(pred_abstain["gold"].isna().sum(), len(pred_abstain)),
        "환각 비율": _ratio(gold_abstain["pred"].notna().sum(), len(gold_abstain)),
        "근거 추적 정확도": _ratio(traced.sum(), len(pred_scored)),
        "출처 정확도": _ratio(found["source_match"].fillna(False).astype(bool).sum(), len(found)),
        "점수-근거 불일치": _ratio(table["inconsistent"].sum(), len(table)),
    }
    # 분모(문항 수). '차이 없음' 판정에 쓴다.
    out.update({"n:정확 일치": len(both), "n:점수 재현율": len(gold_scored), "n:판단 보류 재현율": len(gold_abstain),
                "n:판단 보류 정밀도": len(pred_abstain), "n:환각 비율": len(gold_abstain),
                "n:근거 추적 정확도": len(pred_scored), "n:출처 정확도": len(found), "n:점수-근거 불일치": len(table),
                "n:±1 일치": len(both)})
    retrieved = table["retrieved_gold"].dropna()
    if len(retrieved):
        out["검색 재현율"] = _ratio(sum(r[0] for r in retrieved), sum(r[1] for r in retrieved))
    return out


def load_results(raw_dir: Path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(raw_dir.glob("*_w*_r*.json"))]


def summarize(results: list[dict], gold: pd.DataFrame) -> pd.DataFrame:
    """조건별로 실행(주×반복)마다 지표를 구한 뒤 평균과 표준편차를 낸다."""
    runs = []
    for result in results:
        table = item_table(result, gold)
        runs.append({"condition": result["condition"], "label": result["label"], "week": result["week"],
                     "repeat": result["repeat"], "items": len(table), **metrics(table)})
    runs = pd.DataFrame(runs)
    if runs.empty:
        return runs
    metric_cols = [c for c in runs.columns if c not in ("condition", "label", "week", "repeat", "items")]
    rows = []
    for (cond, label), group in runs.groupby(["condition", "label"], sort=False):
        row = {"condition": cond, "조건": label, "주 수": group["week"].nunique(),
               "반복 수": group["repeat"].nunique(), "실행 수": len(group), "문항 판단 수": int(group["items"].sum())}
        for c in metric_cols:
            mean, std = group[c].mean(), group[c].std(ddof=0)
            row[c] = f"{mean:.2f}" + (f" ± {std:.2f}" if len(group) > 1 else "")
        rows.append(row)
    return pd.DataFrame(rows)
