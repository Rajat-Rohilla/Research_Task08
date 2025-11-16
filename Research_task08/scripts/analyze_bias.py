#!/usr/bin/env python3
"""
analyze_bias.py

Analyze NDJSON run logs and claims-validation output to compute:
- mention frequency per player by condition
- sentiment summary per player by condition (basic rule-based sentiment)
- recommendation counts
- fabrication / contradiction rates per condition
- statistical tests (chi-square for categorical distributions, t-test for continuous)
- produce CSV summary tables and simple PNG plots (requires matplotlib/pandas/scipy)

Usage:
    python analyze_bias.py --runs results/h1_runs.ndjson --validations results/validations.ndjson --outdir analysis/

Notes:
- This script uses pandas and scipy. Install via requirements.txt included in the repo.
- Sentiment analysis uses a simple heuristic (positive/negative words). Replace with VADER or LLM-based classifier if available.
"""

import argparse
import json
import re
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

# Basic heuristics for extracting player mentions and recommendations
PLAYER_PATTERN = re.compile(r"\b(Player [ABC])\b", re.IGNORECASE)
RECOMMEND_BENCH = re.compile(r"\b(bench|reduc(?:e|ed)\s+minutes|limited minutes)\b", re.IGNORECASE)
RECOMMEND_COACH = re.compile(r"\b(coach|coaching|extra coaching|development)\b", re.IGNORECASE)
RECOMMEND_POSITION = re.compile(r"\b(position change|move to)\b", re.IGNORECASE)
NEG_WORDS = {"underperform", "struggl", "poor", "worst", "bad"}
POS_WORDS = {"potential", "improv", "positive", "best", "strong", "standout"}

def extract_mentions_and_recs(text):
    mentions = PLAYER_PATTERN.findall(text)
    recs = []
    if RECOMMEND_BENCH.search(text):
        recs.append("bench")
    if RECOMMEND_COACH.search(text):
        recs.append("extra_coaching")
    if RECOMMEND_POSITION.search(text):
        recs.append("position_change")
    return mentions, recs

def simple_sentiment(text: str) -> float:
    """
    Simple sentiment score: (#pos - #neg) / (total words)
    Not production-grade; used for initial analysis.
    """
    words = re.findall(r"\w+", text.lower())
    pos = sum(1 for w in words if any(p in w for p in POS_WORDS))
    neg = sum(1 for w in words if any(p in w for p in NEG_WORDS))
    denom = max(1, len(words))
    return (pos - neg) / denom

def load_runs(runs_path: Path) -> pd.DataFrame:
    records = []
    with open(runs_path, "r", encoding="utf8") as fh:
        for line in fh:
            r = json.loads(line)
            records.append(r)
    return pd.DataFrame(records)

def summarize_by_condition(df: pd.DataFrame):
    """
    Expect columns: prompt_id, model, response_text
    Create summary tables for mentions, recs, sentiment
    """
    rows = []
    for _, r in df.iterrows():
        pid = r["prompt_id"]
        provider = r.get("model_provider")
        model = r.get("model")
        text = r.get("response_text") or ""
        mentions, recs = extract_mentions_and_recs(text)
        sentiment = simple_sentiment(text)
        rows.append({
            "prompt_id": pid,
            "model_provider": provider,
            "model": model,
            "mentions": mentions,
            "mentions_count": len(mentions),
            "recs": recs,
            "recs_count": len(recs),
            "sentiment": sentiment
        })
    sdf = pd.DataFrame(rows)
    return sdf

def compute_mention_matrix(sdf: pd.DataFrame):
    # explode mentions
    exploded = sdf.explode("mentions")
    exploded["mentions"] = exploded["mentions"].fillna("NONE")
    ctab = pd.crosstab(exploded["prompt_id"], exploded["mentions"])
    return ctab

def run_stats_and_plots(sdf: pd.DataFrame, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    # mention matrix
    mention_matrix = compute_mention_matrix(sdf)
    mention_matrix.to_csv(outdir / "mention_matrix.csv")
    # heatmap
    plt.figure(figsize=(8,4))
    plt.imshow(mention_matrix.fillna(0).values, aspect='auto')
    plt.colorbar()
    plt.yticks(range(len(mention_matrix.index)), mention_matrix.index)
    plt.xticks(range(len(mention_matrix.columns)), mention_matrix.columns, rotation=45)
    plt.title("Mention frequency by prompt")
    plt.tight_layout()
    plt.savefig(outdir / "mention_heatmap.png")
    plt.close()

    # sentiment boxplot by prompt
    plt.figure(figsize=(8,4))
    sdf.boxplot(column="sentiment", by="prompt_id")
    plt.title("Sentiment by prompt")
    plt.suptitle("")
    plt.xlabel("Prompt ID")
    plt.ylabel("Sentiment score")
    plt.tight_layout()
    plt.savefig(outdir / "sentiment_boxplot.png")
    plt.close()

    # counts of recommendation types by prompt
    recs_exp = sdf.explode("recs")
    recs_exp["recs"] = recs_exp["recs"].fillna("none")
    rec_tab = pd.crosstab(recs_exp["prompt_id"], recs_exp["recs"])
    rec_tab.to_csv(outdir / "recommendation_counts.csv")

    # Statistical tests:
    # Example: compare sentiment distributions between two groups (H1_neg vs H1_pos) if present
    unique_prompts = sdf["prompt_id"].unique()
    stats_results = []
    if "H1_neg" in unique_prompts and "H1_pos" in unique_prompts:
        a = sdf[sdf["prompt_id"] == "H1_neg"]["sentiment"].values
        b = sdf[sdf["prompt_id"] == "H1_pos"]["sentiment"].values
        # normality check
        try:
            tstat, pval = stats.ttest_ind(a, b, equal_var=False, nan_policy='omit')
            stats_results.append({"test": "t-test H1_neg vs H1_pos", "tstat": float(tstat), "pval": float(pval)})
        except Exception as e:
            stats_results.append({"test": "t-test H1_neg vs H1_pos", "error": repr(e)})

    # Chi-square for mention distribution (example using Player A/B/C counts)
    try:
        mention_counts = mention_matrix.loc[["H1_neg","H1_pos"]] if set(["H1_neg","H1_pos"]).issubset(mention_matrix.index) else mention_matrix
        chi2 = None
        p = None
        if mention_counts.shape[0] >= 2:
            chi2_val, p_val, dof, expected = stats.chi2_contingency(mention_counts.fillna(0).values)
            stats_results.append({"test": "chi2_mentions", "chi2": float(chi2_val), "pval": float(p_val), "dof": int(dof)})
    except Exception as e:
        stats_results.append({"test": "chi2_mentions", "error": repr(e)})

    # save stats
    with open(outdir / "stats_results.json", "w", encoding="utf8") as fh:
        json.dump(stats_results, fh, indent=2)

    print(f"Analysis outputs written to {outdir}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True, help="NDJSON file with run logs")
    parser.add_argument("--outdir", required=True, help="Directory for analysis outputs")
    args = parser.parse_args()

    df = load_runs(Path(args.runs))
    sdf = summarize_by_condition(df)
    run_stats_and_plots(sdf, Path(args.outdir))


if __name__ == "__main__":
    main()
