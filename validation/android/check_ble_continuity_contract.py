#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
POLICY = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt"
ESTIMATOR = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt"
FUSION = ROOT / "apps/mobile/src/rangeFusion.ts"
GRAPH = ROOT / "apps/mobile/src/geometryDiagnostics.ts"
APP = ROOT / "apps/mobile/App.tsx"
APP_JSON = ROOT / "apps/mobile/app.json"
PROFILES = ROOT / "calibration/ble-range-calibration-profiles.json"
P0C = ROOT / "validation/fixtures/ble-range/p0c-calibration-summary.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"BLE CONTINUITY CONTRACT FAILED: {message}")


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def main() -> None:
    module = MODULE.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")
    estimator = ESTIMATOR.read_text(encoding="utf-8")
    fusion = FUSION.read_text(encoding="utf-8")
    graph = GRAPH.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    app_json = json.loads(APP_JSON.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    p0c = json.loads(P0C.read_text(encoding="utf-8"))

    # The dev-6 physical profile is frozen. Continuity work must not relax physics.
    active = next(p for p in profiles["profiles"] if p["profile_id"] == profiles["active_profile_id"])
    expected = p0c["profile"]
    require(active["profile_id"] == "android-ble-lab-v1", "active profile changed")
    require(active["validated"] is True, "validated profile disabled")
    require(active["physical_confidence"] == "COARSE", "confidence raised above/below approved COARSE state")
    require(close(float(active["rssi_at_1m_dbm"]), -69.19), "RSSI@1m changed")
    require(close(float(active["path_loss_exponent"]), 3.62), "path-loss exponent changed")
    require(close(float(active["valid_distance_min_m"]), 0.5), "minimum domain changed")
    require(close(float(active["valid_distance_max_m"]), 5.0), "maximum domain changed")
    require(close(float(expected["rssi_at_1m_dbm"]), -69.19), "P0c fixture changed unexpectedly")
    require(float(active["validation_metrics"]["mae_m"]) <= 2.0, "dev-6 MAE regression gate lost")
    require(float(active["validation_metrics"]["max_error_m"]) <= 3.0, "dev-6 max-error gate lost")
    require("coerceIn(0.5, 5.0)" not in estimator + module, "silent range clamp reintroduced")

    # Bounded temporal state machine.
    for token in [
        "FRESH_MS = 5_000L",
        "HOLDOVER_MAX_MS = 10_000L",
        "HARD_EXPIRY_MS = 10_000L",
        "SIGMA_AGING_M_PER_S = 0.15",
        "BleRangeTemporalState.HOLDOVER",
        "BleRangeTemporalState.EXPIRED",
    ]:
        require(token in policy, f"temporal policy token missing: {token}")
    require("holdoverEligible" in policy and "agedSigma" in policy, "holdover helpers missing")

    # RSSI 127/invalids must be rejected BEFORE entering the estimator queue.
    validator_pos = module.find("BleRangeEstimator.isValidBleRssi(result.rssi.toDouble())")
    queue_add_pos = module.find("queue.addLast(RssiSample(result.rssi, advertisedTx, now))")
    require(validator_pos >= 0 and queue_add_pos >= 0 and validator_pos < queue_add_pos, "RSSI validation is not pre-queue")
    require("invalidRssiEventsByIdentity" in module, "invalid RSSI diagnostic ring missing")
    require("invalidRssiTotalCount" in module, "invalid RSSI total counter missing")
    require("latest_invalid_rssi_dbm" in module, "invalid RSSI diagnostic field missing")
    require("median_valid_rssi_dbm" in module, "valid-only median missing")
    require("rssi_samples_dbm\", JSONArray(fresh.map { it.rssi })" in module, "calibration snapshot does not use valid-only queue")

    for token in [
        "raw_sample_count_5s",
        "valid_rssi_sample_count_5s",
        "invalid_rssi_sample_count_5s",
        "raw_sample_count_8s",
        "valid_rssi_sample_count_8s",
        "invalid_rssi_sample_count_8s",
    ]:
        require(token in module, f"sample accounting missing: {token}")

    # Last-valid state, bounded holdover, aging and explicit invalidation.
    for token in [
        "lastValidRangeByPeer",
        "LastValidRangeState",
        "LAST_VALID_HOLDOVER",
        "bounded BLE metric HOLDOVER",
        "BleContinuityPolicy.agedSigma",
        "FabricRuntime.lastValidRangeByPeer.remove(peerId)",
        "OUT_OF_DOMAIN_LOW",
        "OUT_OF_DOMAIN_HIGH",
    ]:
        require(token in module + policy, f"holdover contract missing: {token}")
    require("FabricRuntime.lastValidRangeByPeer.remove(nodeId)" in module, "peer expiry does not invalidate cached range")

    # Scanner restarts are based on GLOBAL callback silence, not isolated peer gaps.
    require("scanCallbackHealth" in module, "scanner health classifier missing")
    require("SCANNER_CALLBACK_STALLED" in module, "global callback stalled state missing")
    require("isolated peer gaps never trigger scanner restart" in module, "single-peer gap protection missing")
    require("peer_gap_state" in module and "PEER_TEMPORARILY_NOT_OBSERVED" in module, "per-peer gap diagnostics missing")

    # Fused solver inputs must preserve temporal truth and reject expired/disagreement evidence.
    for token in [
        "range_temporal_state",
        "HOLDOVER_MAX_MS = 10_000",
        "source_temporal_states",
        "oldest_source_age_ms",
        "REJECTED_DISAGREEMENT",
        "RECIPROCAL_INVERSE_VARIANCE",
        "SINGLE_DIRECTION_CONSERVATIVE",
    ]:
        require(token in fusion, f"fusion temporal contract missing: {token}")
    for token in [
        "fresh_metric_edge_count",
        "holdover_metric_edge_count",
        "oldest_metric_edge_age_ms",
        "geometry_temporal_quality",
        "HOLDOVER_DOMINANT",
        "MIXED_FRESH_HOLDOVER",
    ]:
        require(token in graph, f"geometry temporal diagnostics missing: {token}")
    require("reciprocalState !== 'REJECT'" in graph, "REJECT may enter metric graph")
    require("temporalState === 'FRESH' || temporalState === 'HOLDOVER'" in graph, "graph does not gate temporal states")

    # Run-scoped uptime must distinguish fresh from usable holdover geometry.
    for token in [
        "fresh_metric_range_uptime_percent",
        "usable_metric_range_uptime_percent",
        "holdover_metric_uptime_percent",
        "snapshot_wall_ms",
        "snapshot_elapsed_ms",
    ]:
        require(token in module, f"validation-run temporal metric missing: {token}")
    require("export_auto_finalized_validation_run" in app, "share export does not report auto-finalization")
    require("BodyFinderNative.endValidationRun()" in app, "share does not auto-finalize active run")

    # Product/release truth.
    require("0.2.0-experimental.7" in app, "mobile build is not experimental.7")
    require(app_json["expo"]["android"]["versionCode"] == 7, "Android versionCode must be 7")
    require(app_json["expo"]["extra"]["releaseIteration"] == "experimental.7", "releaseIteration must be experimental.7")
    require("HUMAN_SCANNING_ENABLED = false" in app, "human scanning must remain blocked until continuity gate passes")

    # Synthetic policy timeline. This is intentionally conservative and mirrors the code constants.
    fresh_ms = 5_000
    holdover_max = 10_000
    hard_expiry = 10_000
    aging = 0.15
    base_sigma = 1.0

    def state(current_metric: bool, age_ms: int | None, invalidating: bool = False) -> str:
        if invalidating:
            return "INVALID"
        if current_metric:
            return "FRESH"
        if age_ms is None:
            return "ACQUIRING"
        if age_ms <= holdover_max:
            return "HOLDOVER"
        if age_ms <= hard_expiry:
            return "STALE"
        return "EXPIRED"

    require(state(True, 0) == "FRESH", "fresh transition failed")
    require(state(False, fresh_ms + 1) == "HOLDOVER", "holdover transition failed")
    require(state(False, holdover_max) == "HOLDOVER", "holdover boundary failed")
    require(state(False, hard_expiry + 1) == "EXPIRED", "hard expiry failed")
    require(state(False, 6_000, invalidating=True) == "INVALID", "invalidating evidence failed")
    sigmas = [base_sigma + aging * (age / 1000.0) for age in (0, 2_000, 5_000, 9_000)]
    require(all(b >= a for a, b in zip(sigmas, sigmas[1:])), "sigma aging is not monotonic")
    require(sigmas[-1] > base_sigma, "holdover sigma does not increase")

    print(json.dumps({
        "contract": "experimental.7 bounded BLE metric continuity",
        "profile_id": active["profile_id"],
        "profile_frozen": True,
        "fresh_ms": fresh_ms,
        "holdover_max_ms": holdover_max,
        "hard_expiry_ms": hard_expiry,
        "sigma_aging_m_per_s": aging,
        "invalid_rssi_prequeue_filtered": True,
        "raw_valid_invalid_counters": True,
        "global_scan_stall_only_restart": True,
        "human_scanning_enabled": False,
    }, indent=2))


if __name__ == "__main__":
    main()
