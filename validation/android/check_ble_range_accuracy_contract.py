#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
ESTIMATOR = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt"
SERVICE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderFieldService.kt"
MANIFEST = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/AndroidManifest.xml"
APP = ROOT / "apps/mobile/App.tsx"
GRAPH = ROOT / "apps/mobile/src/geometryDiagnostics.ts"
PROFILE = ROOT / "calibration/ble-range-calibration-profiles.json"
FIXTURE = ROOT / "validation/fixtures/ble-range/t2-t4b-screening.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    module = MODULE.read_text(encoding="utf-8")
    estimator = ESTIMATOR.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    graph = GRAPH.read_text(encoding="utf-8")
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    require("coerceIn(0.20, 30.0)" not in module, "experimental.4 silent 30m clamp is still present")
    require(not re.search(r"10\.0\.pow\(\(tx\s*-\s*rssi\)", module), "TxPower is still being used as RSSI@1m")
    require("advertised_tx_power_semantics" in module, "TxPower diagnostic semantics missing")
    require("metric_valid" in module and "raw_distance_m" in module, "range truth fields missing")
    require("PROXIMITY_ONLY" in estimator, "proximity-only state missing")
    require("SATURATED_HIGH" in estimator and "SATURATED_LOW" in estimator, "saturation states missing")
    require("activeProfile.validated" in estimator, "unvalidated profile metric gate missing")
    require("metric_valid" in graph and "metric_edge_pairs" in graph, "geometry metric-edge gate missing")
    require("GEOMETRY UNTRUSTED / NO METRIC RANGE" in app, "truthful no-metric UI missing")
    require("startValidationRun" in app and "validation_run" in app, "validation run UI/export missing")
    require("BodyFinderFieldService" in service and "PARTIAL_WAKE_LOCK" in service, "field service/wake strategy missing")
    require("FOREGROUND_SERVICE_CONNECTED_DEVICE" in manifest, "connected-device foreground service manifest permission missing")

    active = next(p for p in profile["profiles"] if p["profile_id"] == profile["active_profile_id"])
    require(active["validated"] is False, "screening profile must remain unvalidated until multi-distance physical calibration passes")
    require(profile["policy"]["silent_distance_clamp"] is False, "profile policy permits silent clamp")
    require(profile["policy"]["ground_truth_used_at_runtime"] is False, "ground truth must not be a runtime input")
    require(fixture["runtime_input"] is False, "physical evidence fixture is incorrectly marked as runtime input")

    # Reproduce the physical reason experimental.4 saturated: these representative values
    # all produce raw values beyond the old 30 m bound when advertised TxPower is misused.
    old_raw = []
    for row in fixture["representative_observations"]:
        raw = 10.0 ** ((row["advertised_tx_power_dbm"] - row["rssi_dbm"]) / (10.0 * 2.2))
        old_raw.append(raw)
    require(any(v > 30.0 for v in old_raw), "fixture no longer reproduces the old saturation cause")

    # New screening prior is diagnostic only; even if its raw estimate lies in-domain it
    # cannot become a metric edge while validated=false.
    rssi1m = float(active["rssi_at_1m_dbm"])
    n = float(active["path_loss_exponent"])
    require(n > 0, "profile path-loss exponent must be physically positive")
    new_raw = [10.0 ** ((rssi1m - row["rssi_dbm"]) / (10.0 * n)) for row in fixture["representative_observations"]]
    require(all(math.isfinite(v) and v > 0 for v in new_raw), "new diagnostic model produced non-finite raw distances")

    print(json.dumps({
        "contract": "experimental.5 BLE range truth",
        "old_raw_max_m": max(old_raw),
        "new_diagnostic_raw_min_m": min(new_raw),
        "new_diagnostic_raw_max_m": max(new_raw),
        "active_profile_validated": active["validated"],
        "metric_ble_rssi_enabled": False,
    }, indent=2))


if __name__ == "__main__":
    main()
