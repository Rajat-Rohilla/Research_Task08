# -*- coding: utf-8 -*-
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, Any, List

# ---------------------
# Utility
# ---------------------
def to_int(val):
    try:
        return int(val)
    except:
        return None

# ---------------------
# Claim Patterns
# ---------------------
NUMERIC_PATTERNS = [
    (re.compile(r"(Player [ABC])\s+(?:scor(?:ed|es)|has)\s+(\d+)\s+goals?", re.IGNORECASE), "HAS_GOALS"),
    (re.compile(r"(Player [ABC])\s+has\s+(\d+)\s+assists?", re.IGNORECASE), "HAS_ASSISTS"),
    (re.compile(r"(Player [ABC])\s+has\s+(\d+)\s+shots?", re.IGNORECASE), "HAS_SHOTS"),
    (re.compile(r"(Player [ABC])\s+has\s+(\d+)\s+turnovers?", re.IGNORECASE), "HAS_TURNOVERS"),
]

COMPARATIVE_PATTERNS = [
    (re.compile(r"(Player [ABC]).*most assists", re.IGNORECASE), "MOST_ASSISTS"),
    (re.compile(r"(Player [ABC]).*most shots", re.IGNORECASE), "MOST_SHOTS"),
    (re.compile(r"(Player [ABC]).*most turnovers|highest number of turnovers", re.IGNORECASE), "MOST_TURNOVERS"),
    (re.compile(r"(Player [ABC]).*least goals", re.IGNORECASE), "LEAST_GOALS"),
]

# ---------------------
# Load Ground Truth
# ---------------------
def load_ground_truth(csv_path: Path) -> Dict[str, Dict[str, Any]]:
    gt = {}
    with open(csv_path, newline="", encoding="utf8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            player = row.get("player") or row.get("Player") or row.get("PLAYER")
            if not player:
                continue

            def parse_num(x):
                if x is None or x == "":
                    return None
                try:
                    return int(x)
                except:
                    try:
                        return float(x)
                    except:
                        return None

            parsed = {}

            # Normalize and map the known stat columns
            # Raw headers: Goals, Assists, Shots, Turn Overs
            goals_val = row.get("Goals")
            assists_val = row.get("Assists")
            shots_val = row.get("Shots")
            to_val = row.get("Turn Overs")

            if goals_val is not None:
                parsed["goals"] = parse_num(goals_val)
            if assists_val is not None:
                parsed["assists"] = parse_num(assists_val)
            if shots_val is not None:
                parsed["shots"] = parse_num(shots_val)
            if to_val is not None:
                parsed["turnovers"] = parse_num(to_val)

            # Keep everything else as-is if you want
            for k, v in row.items():
                if k not in ("Goals", "Assists", "Shots", "Turn Overs", "Player", "player", "PLAYER"):
                    parsed[k] = v

            gt[player.strip()] = parsed

    return gt


# ---------------------
# Extract Claims
# ---------------------
def extract_claims(response_text: str) -> List[Dict[str, Any]]:
    claims = []
    # numeric claims
    for pattern, ctype in NUMERIC_PATTERNS:
        for m in pattern.finditer(response_text):
            claims.append({"claim_type": ctype, "claim_text": m.group(0), "groups": list(m.groups())})
    # comparative claims
    for pattern, ctype in COMPARATIVE_PATTERNS:
        for m in pattern.finditer(response_text):
            player_name = m.group(1).strip() if m.group(1) else None
            claims.append({"claim_type": ctype, "claim_text": m.group(0), "groups": [player_name] if player_name else []})
    return claims

# ---------------------
# Validate Claims
# ---------------------
def validate_claim(claim: Dict[str, Any], gt: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    ctype = claim.get("claim_type")
    groups = claim.get("groups") or []
    status = "unverifiable"
    evidence = None

    # safely extract player if present
    player_raw = groups[0] if len(groups) > 0 else None
    player = player_raw.strip() if player_raw else None

    try:
        # Numeric claims
        if ctype in ["HAS_GOALS", "HAS_ASSISTS", "HAS_SHOTS", "HAS_TURNOVERS"]:
            metric_map = {
                "HAS_GOALS": "goals",
                "HAS_ASSISTS": "assists",
                "HAS_SHOTS": "shots",
                "HAS_TURNOVERS": "turnovers",
            }

            metric = metric_map[ctype]
            claimed = int(groups[1]) if len(groups) > 1 else None
            if player and claimed is not None:
                actual = gt.get(player)
                if actual and actual.get(metric) is not None:
                    actual_val = int(actual[metric])
                    status = "true" if actual_val == claimed else "false"
                    evidence = {f"actual_{metric}": actual_val}
                else:
                    status = "unverifiable"
                    evidence = {"error": f"No data for player {player}"}
            else:
                status = "unverifiable"
                evidence = {"error": "Player or claimed value missing"}

        # Comparative claims
        elif ctype in ["MOST_SHOTS", "MOST_ASSISTS", "MOST_TURNOVERS", "LEAST_GOALS"]:
            metric_map = {
                "MOST_SHOTS": "shots",
                "MOST_ASSISTS": "assists",
                "MOST_TURNOVERS": "turnovers",
                "LEAST_GOALS": "goals",
            }

            metric = metric_map[ctype]
            # collect all players that have a numeric value for this metric
            values = [(p, to_int(v.get(metric))) for p, v in gt.items() if v.get(metric) is not None]

            if values:
                # max for MOST_*, min for LEAST_GOALS
                comp_val = min([v for _, v in values]) if ctype == "LEAST_GOALS" else max([v for _, v in values])
                comp_players = [p for p, v in values if v == comp_val]

                if player:
                    status = "true" if player in comp_players else "false"
                else:
                    status = "unverifiable"
                evidence = {"metric": metric, "value": comp_val, "players": comp_players}
            else:
                status = "unverifiable"
                evidence = {"error": "No valid numeric data in ground truth"}

    except Exception as e:
        status = "error"
        evidence = {"error": repr(e)}

    return {"claim": claim, "validation": {"status": status, "evidence": evidence}}

# ---------------------
# Main Script
# ---------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt", required=True, help="Ground truth CSV file path")
    parser.add_argument("--runs", required=True, help="NDJSON runs file")
    parser.add_argument("--out", required=True, help="Output NDJSON claims validation file")
    args = parser.parse_args()

    gt = load_ground_truth(Path(args.gt))

    with open(args.runs, "r", encoding="utf8") as fh_in, open(args.out, "w", encoding="utf8") as fh_out:
        for line in fh_in:
            run = json.loads(line)
            resp = run.get("response_text") or ""
            claims = extract_claims(resp)
            validations = [validate_claim(c, gt) for c in claims]
            result = {
                "run_id": run.get("run_id"),
                "prompt_id": run.get("prompt_id"),
                "model": run.get("model"),
                "provider": run.get("model_provider"),
                "response_text": resp,
                "claims_extracted": claims,
                "validations": validations
            }
            fh_out.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(f"Validations written to {args.out}")

if __name__ == "__main__":
    main()
