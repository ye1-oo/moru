"""실험 B 지표.

문항 단위(한 주 48문항)로 정답과 비교한다.
- 정확 일치 / ±1 일치: 정답 점수가 있고 모델도 점수를 준 문항 기준
- 판단 보류 재현율: 정답이 판단 보류인 문항을 보류로 맞춘 비율. 정밀도: 모델이 보류한 문항 중 정답도 보류인 비율
- 환각 비율: 정답이 판단 보류인 문항 중 점수를 매긴 비율 (= 1 - 판단 보류 재현율)
- 점수 재현율: 정답 점수가 있는 문항 중 모델이 점수를 준 비율(과도한 보류 확인용)
- 근거 추적 정확도: 모델이 점수를 준 문항 중 근거 문장이 실제 일기·캡션에 있고 날짜도 그 기록과 같은 비율
- 출처 정확도: 근거 문장이 확인된 문항 중 출처(parent/caption)가 맞는 비율
- 검색 재현율: 정답 근거 일기가 문항의 top-k 검색 결과에 든 비율
- 단서-문항 연결 정밀도: 점수를 준 문항 중 근거 문장이 들어 있는 기록(일기)이 정답 relevance 라벨에서 그 문항과
  관련된 기록인 비율. 근거 문장을 기록에서 찾지 못하면(추적 불가) 틀린 연결로 센다.
  근거 문장이 [부모 일기]에서 찾아졌는지 [캡션]에서 찾아졌는지로 나눠서도 낸다.
- 단서-문항 연결 재현율: 정답에서 관련 기록이 있는 (주, 문항) 중 그 관련 기록을 근거로 연결한 비율.
  정답 사례 유형으로 나눈다: 일기 단서(parent, ambiguous_time), 캡션 단서(caption_only), 둘 다(both, conflict).
"""

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

from moru import config

GOLD_WEEKLY = config.GOLD_DIR / "child_A_weekly.csv"
# 3주차(촘촘한 기록)는 별도 파일로 두고 실행 전에 고정했다(2026-11-10).
GOLD_FILES = [GOLD_WEEKLY, config.GOLD_DIR / "child_A_w3_weekly.csv"]
RELEVANCE_FILES = [config.GOLD_DIR / "child_A_relevance.csv", config.GOLD_DIR / "child_A_w3_relevance.csv"]
CLUE_GROUP = {"parent": "일기 단서", "ambiguous_time": "일기 단서", "caption_only": "캡션 단서",
              "both": "둘 다", "conflict": "둘 다"}


def load_relevance() -> dict[str, set[str]]:
    """문항 → 정답상 관련 기록(diary_id) 집합. 주는 diary_id로 구분된다."""
    rel: dict[str, set[str]] = {}
    for path in RELEVANCE_FILES:
        if path.exists():
            for row in csv.DictReader(path.open(encoding="utf-8")):
                if row["relevant"] == "1":
                    rel.setdefault(row["item_id"], set()).add(row["diary_id"])
    return rel


def load_gold() -> pd.DataFrame:
    gold = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False) for p in GOLD_FILES if p.exists()],
                     ignore_index=True)
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
            "inconsistent": f["inconsistent"], "found_in": f.get("found_in"),
            "gold_diaries": ";".join(gold_diaries),
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


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def link_metrics(table: pd.DataFrame, relevance: dict[str, set[str]]) -> dict:
    """단서-문항 연결 정밀도·재현율(정답 relevance 라벨 기준). table은 한 실행(한 주)의 item_table."""
    links = []  # (연결 출처, 맞는가)
    for _, r in table[table["pred"].notna()].iterrows():
        hits = [h.split(":") for h in _text(r["found_in"]).split(";") if h]
        week_rel = {d for d in relevance.get(r["item_id"], set()) if d in set(r["gold_diaries"].split(";"))} \
            if r["gold_diaries"] else set()
        if not hits:
            links.append(("추적 불가", False))
            continue
        good = [s for d, s in hits if d in week_rel]
        src = good[0] if good else hits[0][1]
        links.append(({"parent": "일기 단서", "caption": "캡션 단서"}[src], bool(good)))
    out = {"연결 정밀도": _ratio(sum(ok for _, ok in links), len(links)), "n:연결 정밀도": len(links)}
    for group in ("일기 단서", "캡션 단서"):
        mine = [ok for g, ok in links if g == group]
        out[f"연결 정밀도({group})"] = _ratio(sum(mine), len(mine))
        out[f"n:연결 정밀도({group})"] = len(mine)
    out["n:추적 불가"] = sum(g == "추적 불가" for g, _ in links)
    gold_pairs = table[table["gold_diaries"] != ""]
    found = []
    for _, r in gold_pairs.iterrows():
        diaries = {h.split(":")[0] for h in _text(r["found_in"]).split(";") if h} if r["pred"] is not None and not pd.isna(r["pred"]) else set()
        found.append((CLUE_GROUP.get(r["case"], "일기 단서"), bool(diaries & set(r["gold_diaries"].split(";")))))
    out["연결 재현율"] = _ratio(sum(ok for _, ok in found), len(found))
    out["n:연결 재현율"] = len(found)
    for group in ("일기 단서", "캡션 단서", "둘 다"):
        mine = [ok for g, ok in found if g == group]
        out[f"연결 재현율({group})"] = _ratio(sum(mine), len(mine))
        out[f"n:연결 재현율({group})"] = len(mine)
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
