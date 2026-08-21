#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
ACQ = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt"
CONT = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleContinuityPolicy.kt"
SYSTEM = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/SystemRangingApi36.kt"
ESTIMATOR = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleRangeEstimator.kt"
APP = ROOT / "apps/mobile/App.tsx"
APP_JSON = ROOT / "apps/mobile/app.json"
PROFILES = ROOT / "calibration/ble-range-calibration-profiles.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"BLE ACQUISITION CONTRACT FAILED: {message}")


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def main() -> None:
    module = MODULE.read_text(encoding="utf-8")
    acq = ACQ.read_text(encoding="utf-8")
    cont = CONT.read_text(encoding="utf-8")
    system = SYSTEM.read_text(encoding="utf-8")
    estimator = ESTIMATOR.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    app_json = json.loads(APP_JSON.read_text(encoding="utf-8"))
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    active = next(p for p in profiles["profiles"] if p["profile_id"] == profiles["active_profile_id"])

    # Frozen physical/temporal truth.
    require(active["profile_id"] == "android-ble-lab-v1", "active profile changed")
    require(active["validated"] is True, "profile is not validated")
    require(active["physical_confidence"] == "COARSE", "profile confidence changed")
    require(close(float(active["rssi_at_1m_dbm"]), -69.19), "RSSI@1m changed")
    require(close(float(active["path_loss_exponent"]), 3.62), "path-loss exponent changed")
    require(close(float(active["valid_distance_min_m"]), 0.5), "minimum metric domain changed")
    require(close(float(active["valid_distance_max_m"]), 5.0), "maximum metric domain changed")
    require("private const val MIN_SAMPLES_FOR_RANGE = 3" in module, "minSamples was relaxed")
    require("private const val RANGE_FRESHNESS_MS = 5_000L" in module, "freshness window changed")
    require("HOLDOVER_MAX_MS = 10_000L" in cont, "holdover was expanded")
    require("HARD_EXPIRY_MS = 10_000L" in cont, "hard expiry changed")
    require("SIGMA_AGING_M_PER_S = 0.15" in cont, "holdover sigma aging changed")
    require("coerceIn(0.5, 5.0)" not in module + estimator, "silent metric clamp reintroduced")

    # experimental.9 acquisition strategy: controller/manufacturer filtered primary, unfiltered only for bounded recovery.
    for token in [
        "FILTERED_PRIMARY", "UNFILTERED_RECOVERY", "FILTERED_RECOVERY_PROBE", "COOLDOWN", "FAILED_SAFE",
        "ScanSettings.SCAN_MODE_LOW_LATENCY", "setReportDelay(REPORT_DELAY_MS)",
        "ScanSettings.CALLBACK_TYPE_ALL_MATCHES", "ScanSettings.MATCH_MODE_AGGRESSIVE", "ScanSettings.MATCH_NUM_MAX_ADVERTISEMENT",
        "startFilteredScan", "startUnfilteredRecoveryScan", "manufacturerFilter",
        "COHORT_STALL_THRESHOLD_MS = 5_000L", "RECOVERY_UNFILTERED_WINDOW_MS = 10_000L",
        "FILTERED_PROBE_WINDOW_MS = 15_000L", "MIN_RESTART_COOLDOWN_MS = 30_000L",
        "MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3",
    ]:
        require(token in acq, f"adaptive acquisition token missing: {token}")
    require("BleAcquisitionPolicy.startFilteredScan" in module, "primary scanner is not filtered")
    require("BleAcquisitionPolicy.startUnfilteredRecoveryScan" in module, "unfiltered recovery path missing")
    require("getManufacturerSpecificData(MANUFACTURER_ID)" in module and "payloadIdentity(raw)" in module, "Body Finder payload validation missing")
    require("ADVERTISE_TX_POWER_MEDIUM" in module, "advertise Tx power changed")

    # Cohort-specific health and recovery.
    for token in [
        "GLOBAL_SCANNER_HEALTHY", "GLOBAL_SCANNER_STALLED", "BF_COHORT_HEALTHY", "BF_COHORT_SPARSE",
        "BF_COHORT_STALLED", "BF_COHORT_RECOVERING", "maintainAdaptiveScanner", "bodyFinderCohortHealth",
        "strategy_transition_count", "cohort_stall_count", "cohort_recovery_count",
        "cohort_recovery_failure_count", "restart_suppressed_by_cooldown_count",
        "filtered_mode_total_ms", "unfiltered_recovery_total_ms",
    ]:
        require(token in acq + module, f"cohort recovery token missing: {token}")

    # Acquisition telemetry remains available per peer.
    for token in [
        "BleAcquisitionStats", "acquisitionStatsByIdentity", "callback_rate_hz", "valid_callback_rate_hz",
        "mean_interarrival_ms", "max_interarrival_ms", "p50_interarrival_ms", "p95_interarrival_ms",
        "gap_gt_1s_count", "gap_gt_2s_count", "gap_gt_5s_count", "gap_gt_10s_count",
        "run_callback_delta", "run_valid_callback_delta", "run_gap_gt_5s_delta", "run_gap_gt_10s_delta",
        "acquisition_health",
    ]:
        require(token in acq + module, f"acquisition telemetry missing: {token}")
    require("snapshotAcquisitionForValidation" in module, "validation run does not snapshot acquisition counters")
    require("FabricRuntime.snapshotAcquisitionForValidation()" in module, "validation start lacks acquisition baseline")

    # Environment gate and API36 coexistence.
    require("VALIDATION_ENVIRONMENT_INVALID" in module and "BATTERY_SAVER_ON" in module, "Battery Saver validation gate missing")
    on_opened_start = system.find("override fun onOpened()")
    on_open_failed_start = system.find("override fun onOpenFailed", on_opened_start)
    on_opened_body = system[on_opened_start:on_open_failed_start]
    require("registerRealRangeSuccess" not in on_opened_body, "RangingManager onOpened incorrectly resets failure state")
    require("if (distanceM != null) registerRealRangeSuccess()" in system, "real range is not the success gate")
    require("SYSTEM_RANGING_BLE_YIELD_MS = 120_000L" in acq, "BLE yield duration changed")
    require("SYSTEM_RANGING_CLOSES_BEFORE_YIELD = 6L" in acq, "BLE yield close threshold changed")
    for token in ["BLE_ACQUISITION_YIELD", "ble_yield_active", "ble_yield_reason", "closes_since_real_result", "isBleYieldActive"]:
        require(token in system, f"RangingManager BLE-yield token missing: {token}")

    # UI/release truth.
    require("0.2.0-experimental.9" in app, "mobile build is not experimental.9")
    require("const REPORT_VERSION = 11" in app, "report version must be 11")
    require("HUMAN_SCANNING_ENABLED = false" in app, "human scanning must remain blocked")
    require(app_json["expo"]["android"]["versionCode"] == 9, "Android versionCode must be 9")
    require(app_json["expo"]["extra"]["releaseIteration"] == "experimental.9", "release iteration must be experimental.9")

    print(json.dumps({
        "contract": "experimental.9 adaptive BLE acquisition continuity",
        "profile_frozen": True,
        "min_samples": 3,
        "fresh_ms": 5000,
        "holdover_max_ms": 10000,
        "primary_strategy": "FILTERED_PRIMARY",
        "recovery_strategy": "UNFILTERED_RECOVERY",
        "cohort_stall_ms": 5000,
        "restart_cooldown_ms": 30000,
        "max_recovery_attempts_per_5min": 3,
        "ranging_manager_ble_yield_ms": 120000,
        "human_scanning_enabled": False,
    }, indent=2))


if __name__ == "__main__":
    main()
