#!/usr/bin/env python3
"""Static acceptance checks for Android BLE/ranging plumbing.

Experimental.12 preserves the validated COARSE metric/continuity contracts while
adding completed-run integrity, causal recovery provenance and frozen geometry truth.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
APP_JSON = ROOT / "apps/mobile/app.json"
NATIVE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
ACQUISITION = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt"
SYSTEM = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/SystemRangingApi36.kt"
APP = ROOT / "apps/mobile/App.tsx"
VERSION = ROOT / "apps/mobile/src/version.ts"

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"ANDROID RANGING CONTRACT FAILED: {message}")

config = json.loads(APP_JSON.read_text(encoding="utf-8"))
permissions = set(config["expo"]["android"]["permissions"])
for permission in ["android.permission.BLUETOOTH","android.permission.BLUETOOTH_ADMIN","android.permission.BLUETOOTH_SCAN","android.permission.BLUETOOTH_CONNECT","android.permission.BLUETOOTH_ADVERTISE","android.permission.ACCESS_FINE_LOCATION","android.permission.RANGING"]:
    require(permission in permissions, f"missing {permission} in Expo Android permissions")

native = NATIVE.read_text(encoding="utf-8")
acquisition = ACQUISITION.read_text(encoding="utf-8")
system = SYSTEM.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")
version = VERSION.read_text(encoding="utf-8")
for token in ["ScanSettings.SCAN_MODE_LOW_LATENCY","setReportDelay(REPORT_DELAY_MS)","bodyFinderScanResults","binding_state","sample_count_5s","valid_rssi_sample_count_5s","invalid_rssi_sample_count_5s","last_sample_age_ms","address_fingerprint","fallback_evidence_ready","metric_range_ready","range_temporal_state","ADVERTISEMENT_NOT_SEEN","INSUFFICIENT_VALID_SAMPLES","fabric_diagnostics","peer_expire_count","manual_geometry_override"]:
    require(token in native or token in acquisition or token in app, f"missing diagnostic/behavior token {token}")
require("startFilteredScan" in acquisition, "filtered primary scan missing")
require("scanner.startScan(listOf(manufacturerFilter(manufacturerId)), scanSettings(), callback)" in acquisition, "manufacturer-filtered primary scan missing")
require("startUnfilteredRecoveryScan" in acquisition, "unfiltered recovery scan missing")
require("scanner.startScan(null, scanSettings(), callback)" in acquisition, "unfiltered recovery scan missing")
require("setManufacturerData(manufacturerId, prefix, mask)" in acquisition, "manufacturer filter missing")
require("FILTERED_PRIMARY" in acquisition and "UNFILTERED_RECOVERY" in acquisition, "adaptive acquisition strategies missing")
require("BF_COHORT_STALLED" in acquisition, "Body Finder cohort stall state missing")
require('FabricRuntime.bleScanning -> probe("SUPPORTED_UNVERIFIED"' in native, "scanner-only BLE state must be SUPPORTED_UNVERIFIED rather than live ranging")
require("PROXIMITY_ONLY" in native, "proximity fallback state missing")
require("MIN_SAMPLES_FOR_RANGE = 3" in native, "minimum 3-sample gate missing")
require("RANGE_FRESHNESS_MS = 5_000L" in native, "5-second freshness gate missing")
require("WINDOW_RETENTION_MS = 8_000L" in native, "8-second sample window missing")
require("GLOBAL_SCANNER_STALLED" in native or "GLOBAL_SCANNER_STALLED" in acquisition, "global scanner stall classifier missing")
for callback in ["onOpenFailed", "onClosed"]:
    block_match = re.search(rf"override fun {callback}\([^{{]+\) \{{(.*?)\n        \}}", system, re.S)
    require(block_match is not None, f"missing {callback} callback")
    block = block_match.group(1)
    require('session = null' in block, f"{callback} must release dead session")
    require('fingerprint = ""' in block, f"{callback} must clear fingerprint for retry")
    require("registerFailure" in block, f"{callback} must enter bounded retry/circuit-breaker policy")
require("rssiWindows" not in system, "SystemRangingApi36 must not own/clear BLE fallback RSSI windows")
require("hasFreshResult" in system, "fresh system-result predicate missing")
require("last_close_reason" in system, "system close reason diagnostics missing")
require("result_count" in system, "system result count diagnostics missing")
require("CIRCUIT_BREAKER_FAILURES" in system, "bounded failure circuit breaker missing")
require("BLE_ACQUISITION_YIELD" in system, "API36 BLE-acquisition yield missing")
for token in ["getDiagnosticsJson","BLE / ranging diagnostics","Fabric diagnostics","ble_diagnostics","fabric_diagnostics","report_version: REPORT_VERSION"]:
    require(token in app or token in native, f"mobile report/Expert token missing: {token}")
require("0.2.0-experimental.12" in version, "dev12 version truth missing")
for forbidden in ["SET MEASURED POSITION", "Guardar posición", "Set position"]:
    require(forbidden not in app, f"manual geometry UI reintroduced: {forbidden}")
print("Android ranging experimental.12 adaptive acquisition/validation-integrity contract: PASS")
