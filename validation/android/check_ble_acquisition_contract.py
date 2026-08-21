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

    # Primary acquisition strategy.
    for token in [
        "SCAN_STRATEGY = \"LOW_LATENCY_SOFTWARE_FILTERED_ALL_MATCHES\"",
        "ScanSettings.SCAN_MODE_LOW_LATENCY",
        "setReportDelay(REPORT_DELAY_MS)",
        "ScanSettings.CALLBACK_TYPE_ALL_MATCHES",
        "ScanSettings.MATCH_MODE_AGGRESSIVE",
        "ScanSettings.MATCH_NUM_MAX_ADVERTISEMENT",
        "scanner.startScan(null, scanSettings(), callback)",
    ]:
        require(token in acq, f"acquisition strategy missing: {token}")
    require("BleAcquisitionPolicy.startSoftwareFilteredScan(scanner, callback)" in module, "primary scanner does not use software-filtered path")
    require("getManufacturerSpecificData(MANUFACTURER_ID)" in module and "payloadIdentity(raw)" in module, "software Body Finder manufacturer/payload filter missing")
    require("LOW_LATENCY_HARDWARE_FILTER_FALLBACK" in module, "safe hardware-filter fallback missing")
    require("ADVERTISE_TX_POWER_MEDIUM" in module, "advertise Tx power changed; calibration would no longer be comparable")

    # Acquisition telemetry.
    for token in [
        "BleAcquisitionStats", "acquisitionStatsByIdentity", "callback_rate_hz", "valid_callback_rate_hz",
        "mean_interarrival_ms", "max_interarrival_ms", "p50_interarrival_ms", "p95_interarrival_ms",
        "gap_gt_1s_count", "gap_gt_2s_count", "gap_gt_5s_count", "gap_gt_10s_count",
        "run_callback_delta", "run_valid_callback_delta", "run_gap_gt_5s_delta", "run_gap_gt_10s_delta",
        "acquisition_health",
    ]:
        require(token in acq + module, f"acquisition telemetry missing: {token}")
    require("snapshotAcquisitionForValidation" in module, "validation run does not snapshot acquisition counters")
    require("FabricRuntime.snapshotAcquisitionForValidation()" in module, "validation start does not establish acquisition baseline")

    # Global scanner recovery remains separate from isolated peer gaps.
    require("SCANNER_CALLBACK_STALLED" in module, "global scanner stall state missing")
    require("isolated peer gaps never trigger scanner restart" in module, "peer-gap restart protection missing")

    # API36 coexistence: opening a session is no longer a success.
    on_opened_start = system.find("override fun onOpened()")
    on_open_failed_start = system.find("override fun onOpenFailed", on_opened_start)
    on_opened_body = system[on_opened_start:on_open_failed_start]
    require("registerRealRangeSuccess" not in on_opened_body, "RangingManager onOpened incorrectly resets failure state")
    require("if (distanceM != null) registerRealRangeSuccess()" in system, "real range is not the success gate")
    require("SYSTEM_RANGING_BLE_YIELD_MS = 120_000L" in acq, "BLE yield duration changed")
    require("SYSTEM_RANGING_CLOSES_BEFORE_YIELD = 6L" in acq, "BLE yield close threshold changed")
    for token in ["BLE_ACQUISITION_YIELD", "ble_yield_active", "ble_yield_reason", "closes_since_real_result", "isBleYieldActive"]:
        require(token in system, f"RangingManager BLE-yield contract missing: {token}")

    # UI/release truth.
    require("0.2.0-experimental.8" in app, "mobile build is not experimental.8")
    require("const REPORT_VERSION = 10" in app, "report version must be 10")
    require("HUMAN_SCANNING_ENABLED = false" in app, "human scanning must remain blocked")
    require(app_json["expo"]["android"]["versionCode"] == 8, "Android versionCode must be 8")
    require(app_json["expo"]["extra"]["releaseIteration"] == "experimental.8", "release iteration must be experimental.8")
    require("experimental.8 uses low-latency ALL_MATCHES" in app, "Expert acquisition truth is missing")

    print(json.dumps({
        "contract": "experimental.8 BLE acquisition continuity",
        "profile_frozen": True,
        "min_samples": 3,
        "fresh_ms": 5000,
        "holdover_max_ms": 10000,
        "scan_strategy": "LOW_LATENCY_SOFTWARE_FILTERED_ALL_MATCHES",
        "match_mode": "AGGRESSIVE_API23_PLUS",
        "hardware_filter_primary": False,
        "ranging_manager_ble_yield_ms": 120000,
        "human_scanning_enabled": False,
    }, indent=2))


if __name__ == "__main__":
    main()
