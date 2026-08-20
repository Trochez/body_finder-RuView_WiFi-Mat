#!/usr/bin/env python3
"""Fit and validate a Body Finder BLE log-distance profile.

This tool is validation-only. Ground truth is NEVER consumed by the Android runtime.

Input JSON format:
{
  "measurements": [
    {"true_distance_m": 1.0, "rssi_dbm": -66.2, "observer": "pixel7", "peer": "pixel10"},
    ...
  ]
}

The fitter refuses a non-physical path-loss exponent and only marks a profile validated
when holdout-style errors pass the experimental metric gate.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Iterable

MIN_DISTANCES = {0.5, 1.0, 2.0, 3.0, 5.0}
MAE_GATE_M = 2.0
MAX_ERROR_GATE_M = 3.0
MIN_VALID_RSSI_DBM = -127.0
MAX_VALID_RSSI_DBM = 20.0


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_rows(path: Path) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    rows = obj.get("measurements") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        raise SystemExit("Input must contain a measurements[] array")
    clean: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = _finite(row.get("true_distance_m"))
        rssi = _finite(row.get("rssi_dbm"))
        if d is None or rssi is None or d <= 0:
            continue
        if rssi < MIN_VALID_RSSI_DBM or rssi > MAX_VALID_RSSI_DBM:
            continue
        clean.append({**row, "true_distance_m": d, "rssi_dbm": rssi})
    if len(clean) < 10:
        raise SystemExit("At least 10 valid labelled samples are required")
    return clean


def fit(rows: Iterable[dict]) -> tuple[float, float, float]:
    data = list(rows)
    xs = [math.log10(row["true_distance_m"]) for row in data]
    ys = [row["rssi_dbm"] for row in data]
    xbar = statistics.fmean(xs)
    ybar = statistics.fmean(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom <= 1e-12:
        raise ValueError("Distance diversity is insufficient")
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom
    intercept = ybar - slope * xbar
    path_loss_n = -slope / 10.0
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    residual_sigma = math.sqrt(sum(r * r for r in residuals) / max(1, len(residuals) - 2))
    return intercept, path_loss_n, residual_sigma


def predict_distance(rssi: float, rssi_1m: float, n: float) -> float:
    return 10.0 ** ((rssi_1m - rssi) / (10.0 * n))


def metrics(rows: Iterable[dict], rssi_1m: float, n: float) -> dict:
    errors: list[float] = []
    percentage_errors: list[float] = []
    predictions: list[dict] = []
    for row in rows:
        pred = predict_distance(row["rssi_dbm"], rssi_1m, n)
        error = abs(pred - row["true_distance_m"])
        errors.append(error)
        percentage_errors.append(error / row["true_distance_m"] * 100.0)
        predictions.append({
            "true_distance_m": row["true_distance_m"],
            "predicted_distance_m": pred,
            "abs_error_m": error,
            "observer": row.get("observer"),
            "peer": row.get("peer"),
        })
    return {
        "mae_m": statistics.fmean(errors),
        "rmse_m": math.sqrt(statistics.fmean([e * e for e in errors])),
        "median_abs_error_m": statistics.median(errors),
        "max_error_m": max(errors),
        "mape_percent": statistics.fmean(percentage_errors),
        "sample_count": len(errors),
        "predictions": predictions,
    }


def leave_one_distance_out(rows: list[dict]) -> dict:
    distances = sorted(set(round(row["true_distance_m"], 6) for row in rows))
    held_predictions: list[dict] = []
    failures: list[str] = []
    for distance in distances:
        train = [row for row in rows if round(row["true_distance_m"], 6) != distance]
        holdout = [row for row in rows if round(row["true_distance_m"], 6) == distance]
        if len(train) < 5 or not holdout:
            continue
        try:
            intercept, n, _ = fit(train)
        except ValueError as exc:
            failures.append(f"holdout {distance}m: {exc}")
            continue
        if n <= 0.5 or n > 8:
            failures.append(f"holdout {distance}m: non-physical n={n:.3f}")
            continue
        for row in holdout:
            pred = predict_distance(row["rssi_dbm"], intercept, n)
            held_predictions.append({
                "true_distance_m": row["true_distance_m"],
                "predicted_distance_m": pred,
                "abs_error_m": abs(pred - row["true_distance_m"]),
            })
    if not held_predictions:
        return {"valid": False, "failures": failures, "sample_count": 0}
    errors = [row["abs_error_m"] for row in held_predictions]
    return {
        "valid": not failures,
        "failures": failures,
        "sample_count": len(errors),
        "mae_m": statistics.fmean(errors),
        "rmse_m": math.sqrt(statistics.fmean([e * e for e in errors])),
        "max_error_m": max(errors),
    }


def required_distance_coverage(rows: list[dict]) -> dict:
    observed = {round(row["true_distance_m"], 1) for row in rows}
    missing = sorted(MIN_DISTANCES - observed)
    return {"required": sorted(MIN_DISTANCES), "observed": sorted(observed), "missing": missing, "complete": not missing}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--output-profile", type=Path)
    parser.add_argument("--profile-id", default="android-ble-lab-v1")
    args = parser.parse_args()

    rows = load_rows(args.input)
    coverage = required_distance_coverage(rows)
    intercept, n, residual_sigma = fit(rows)
    physical_fit = 0.5 < n <= 8.0
    in_sample = metrics(rows, intercept, n) if physical_fit else None
    holdout = leave_one_distance_out(rows) if physical_fit else {"valid": False, "failures": [f"non-physical path-loss exponent n={n:.4f}"], "sample_count": 0}

    validated = bool(
        physical_fit
        and coverage["complete"]
        and holdout.get("sample_count", 0) > 0
        and holdout.get("mae_m", float("inf")) <= MAE_GATE_M
        and holdout.get("max_error_m", float("inf")) <= MAX_ERROR_GATE_M
    )

    report = {
        "schema_version": 1,
        "input": str(args.input),
        "fit": {
            "rssi_at_1m_dbm": intercept,
            "path_loss_exponent": n,
            "residual_sigma_db": residual_sigma,
            "physical_fit": physical_fit,
        },
        "distance_coverage": coverage,
        "in_sample_metrics": in_sample,
        "leave_one_distance_out": holdout,
        "metric_gate": {"mae_m_lte": MAE_GATE_M, "max_error_m_lte": MAX_ERROR_GATE_M},
        "rssi_input_domain_dbm": {"min": MIN_VALID_RSSI_DBM, "max": MAX_VALID_RSSI_DBM},
        "validated": validated,
        "decision": "METRIC_PROFILE_ACCEPTED" if validated else "PROXIMITY_ONLY_KEEP_METRIC_DISABLED",
        "ground_truth_runtime_input": False,
    }
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.output_profile:
        profile = {
            "schema_version": 1,
            "profile_id": args.profile_id,
            "source": "MULTI_DISTANCE_LAB_FIT",
            "rssi_at_1m_dbm": intercept,
            "rssi_at_1m_sigma_db": max(1.0, residual_sigma),
            "path_loss_exponent": n,
            "path_loss_exponent_sigma": max(0.2, abs(n) * 0.20),
            "valid_distance_min_m": min(row["true_distance_m"] for row in rows),
            "valid_distance_max_m": max(row["true_distance_m"] for row in rows),
            "environment": "INDOOR_OPEN_FIELD_LAB",
            "sample_count": len(rows),
            "validated": validated,
            "validation_note": report["decision"],
            "validation_metrics": None if not validated else {
                "mae_m": holdout["mae_m"],
                "rmse_m": holdout["rmse_m"],
                "max_error_m": holdout["max_error_m"],
                "holdout_count": holdout["sample_count"],
            },
        }
        args.output_profile.parent.mkdir(parents=True, exist_ok=True)
        args.output_profile.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"validated": validated, "decision": report["decision"], "n": n}, indent=2))


if __name__ == "__main__":
    main()
