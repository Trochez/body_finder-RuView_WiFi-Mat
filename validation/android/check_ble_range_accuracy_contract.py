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
APP_JSON = ROOT / "apps/mobile/app.json"
INDEX_TS = ROOT / "apps/mobile/modules/body-finder-native/index.ts"
APP = ROOT / "apps/mobile/App.tsx"
GRAPH = ROOT / "apps/mobile/src/geometryDiagnostics.ts"
FUSION = ROOT / "apps/mobile/src/rangeFusion.ts"
PROFILE = ROOT / "calibration/ble-range-calibration-profiles.json"
PROFILE_SCHEMA = ROOT / "calibration/ble-range-calibration-schema.json"
SCREENING_FIXTURE = ROOT / "validation/fixtures/ble-range/t2-t4b-screening.json"
P0C_FIXTURE = ROOT / "validation/fixtures/ble-range/p0c-calibration-summary.json"
FITTER = ROOT / "validation/analysis/fit_ble_range_profile.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def main() -> None:
    module = MODULE.read_text(encoding="utf-8")
    estimator = ESTIMATOR.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")
    app_json_text = APP_JSON.read_text(encoding="utf-8")
    index_ts = INDEX_TS.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    graph = GRAPH.read_text(encoding="utf-8")
    fusion = FUSION.read_text(encoding="utf-8")
    fitter = FITTER.read_text(encoding="utf-8")
    profiles = json.loads(PROFILE.read_text(encoding="utf-8"))
    json.loads(PROFILE_SCHEMA.read_text(encoding="utf-8"))
    screening_fixture = json.loads(SCREENING_FIXTURE.read_text(encoding="utf-8"))
    p0c = json.loads(P0C_FIXTURE.read_text(encoding="utf-8"))
    app_json = json.loads(app_json_text)

    # Permanent physical-truth guards inherited from experimental.5/6.
    require("coerceIn(0.20, 30.0)" not in module, "experimental.4 silent 30m clamp is still present")
    require("coerceIn(0.5, 5.0)" not in estimator + module, "validated profile has a forbidden silent domain clamp")
    require(not re.search(r"10\.0\.pow\(\(tx\s*-\s*rssi\)", module + estimator), "TxPower is still being used as RSSI@1m")
    require("advertised_tx_power_semantics" in module, "TxPower diagnostic semantics missing")
    require("metric_valid" in module and "raw_distance_m" in module, "range truth fields missing")
    require("CHANGE_WIFI_MULTICAST_STATE" in manifest and "CHANGE_WIFI_MULTICAST_STATE" in app_json_text, "field-service multicast permission missing")
    require("BodyFinderFieldService" in service and "PARTIAL_WAKE_LOCK" in service, "field service/wake strategy missing")
    require("MAX_VALID_RSSI_DBM" in fitter and "MIN_VALID_RSSI_DBM" in fitter, "offline fitter RSSI domain guard missing")

    # Active profile must remain exactly the P0c physically accepted candidate.
    active = next(p for p in profiles["profiles"] if p["profile_id"] == profiles["active_profile_id"])
    expected = p0c["profile"]
    require(active["profile_id"] == "android-ble-lab-v1", "android-ble-lab-v1 is not active")
    require(active["validated"] is True, "android-ble-lab-v1 must be validated")
    require(active["physical_confidence"] == "COARSE", "BLE lab profile must remain COARSE")
    require(close(float(active["rssi_at_1m_dbm"]), float(expected["rssi_at_1m_dbm"])), "RSSI@1m drifted from P0c profile")
    require(close(float(active["path_loss_exponent"]), float(expected["path_loss_exponent"])), "path-loss exponent drifted from P0c profile")
    require(close(float(active["valid_distance_min_m"]), 0.5), "validated minimum distance must be 0.5 m")
    require(close(float(active["valid_distance_max_m"]), 5.0), "validated maximum distance must be 5.0 m")
    metrics = active["validation_metrics"]
    require(float(metrics["mae_m"]) <= 2.0, "P0c MAE no longer passes metric gate")
    require(float(metrics["max_error_m"]) <= 3.0, "P0c max error no longer passes metric gate")
    require(profiles["policy"]["silent_distance_clamp"] is False, "profile policy permits silent clamp")
    require(profiles["policy"]["ground_truth_used_at_runtime"] is False, "ground truth must not be a runtime input")
    require(p0c["runtime_input"] is False and screening_fixture["runtime_input"] is False, "physical evidence fixture marked as runtime input")

    for token in ["android-ble-lab-v1", "RssiAtOneMeterDbm(-69.19)", "PathLossExponent(3.62)", "validDistanceMinM = 0.50", "validDistanceMaxM = 5.0", "validated = true", "physicalConfidence = \"COARSE\""]:
        require(token in estimator, f"runtime profile contract missing: {token}")
    require("OUT_OF_DOMAIN_LOW" in estimator and "OUT_OF_DOMAIN_HIGH" in estimator, "out-of-domain states missing")
    require("VALID_METRIC" in estimator, "validated metric state missing")
    require("value != 127.0" in estimator and "-127.0..20.0" in estimator, "RSSI sentinel/domain filtering missing")
    require("rssi_samples_dbm" in index_ts and "sample !== 127" in index_ts, "calibration snapshot sentinel defense missing")
    require("validationRmseM" in estimator and "holdoutFloor" in estimator, "validation-error sigma floor missing")

    require("RECIPROCAL_INVERSE_VARIANCE" in fusion, "reciprocal inverse-variance fusion missing")
    require("SINGLE_DIRECTION_CONSERVATIVE" in fusion, "single-direction conservative fallback missing")
    require("REJECTED_DISAGREEMENT" in fusion and "rejectThreshold" in fusion, "reciprocal disagreement rejection missing")
    require("1 / (s1 * s1)" in fusion and "1 / (s2 * s2)" in fusion, "inverse variance weights missing")
    require("applyReciprocalFusion" in app and "geometryNodes = fused.nodes" in app, "solver is not consuming fused observations")
    require("reciprocal_fusion" in app and "fused_range_observations" in app, "fusion provenance not exported")
    require("reciprocal_disagreement_count" in graph and "out_of_domain_sample_count" in graph, "measurement-health diagnostics incomplete")

    # experimental.7 must preserve experimental.6 physical accuracy while changing temporal policy only.
    require("0.2.0-experimental.7" in app, "mobile build is not experimental.7")
    require(app_json["expo"]["android"]["versionCode"] == 7, "Android versionCode must be 7")
    require(app_json["expo"]["extra"]["releaseIteration"] == "experimental.7", "releaseIteration must be experimental.7")
    require("VALIDATED_COARSE_BLE_METRIC_0P5_TO_5M" in app, "experimental.7 physical-truth classification missing")

    rssi1m = float(active["rssi_at_1m_dbm"])
    n = float(active["path_loss_exponent"])
    require(0.5 < n <= 8.0, "profile path-loss exponent outside physical sanity gate")
    at_1m = 10.0 ** ((rssi1m - rssi1m) / (10.0 * n))
    require(close(at_1m, 1.0), "profile equation does not return 1 m at RSSI@1m")
    weak_raw = 10.0 ** ((rssi1m - (-110.0)) / (10.0 * n))
    strong_raw = 10.0 ** ((rssi1m - (-40.0)) / (10.0 * n))
    require(weak_raw > 5.0 and strong_raw < 0.5, "out-of-domain synthetic cases do not exercise both boundaries")

    print(json.dumps({
        "contract": "experimental.7 preserves validated coarse BLE metric physics",
        "profile_id": active["profile_id"],
        "rssi_at_1m_dbm": active["rssi_at_1m_dbm"],
        "path_loss_exponent": active["path_loss_exponent"],
        "valid_domain_m": [active["valid_distance_min_m"], active["valid_distance_max_m"]],
        "physical_confidence": active["physical_confidence"],
        "holdout_mae_m": metrics["mae_m"],
        "holdout_max_error_m": metrics["max_error_m"],
        "metric_ble_rssi_enabled": True,
        "silent_clamp": False,
        "sentinel_127_filtered": True,
    }, indent=2))


if __name__ == "__main__":
    main()
