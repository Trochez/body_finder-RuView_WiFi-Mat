#!/usr/bin/env python3
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
TRIGGER = ROOT / "RELEASE_DEV15_TRIGGER.txt"

ap = argparse.ArgumentParser()
ap.add_argument("--no-release-trigger", action="store_true")
args = ap.parse_args()

text = NATIVE.read_text()
old_issue = 'if (expectedKnownPeerCount() < 2) issues += "EXPECTED_BLE_PEERS_LT_2"'
new_issue = 'if (expectedKnownPeerCount() < 1) issues += "EXPECTED_BLE_PEERS_LT_1"'
old_ready = '.put("expected_ble_peers_ready", expectedKnownPeerCount() >= 2)'
new_ready = '.put("expected_ble_peers_ready", expectedKnownPeerCount() >= 1)'

if old_issue in text:
    text = text.replace(old_issue, new_issue, 1)
elif new_issue not in text:
    raise SystemExit("preflight peer-count condition not found")

if old_ready in text:
    text = text.replace(old_ready, new_ready, 1)
elif new_ready not in text:
    raise SystemExit("preflight readiness condition not found")

if 'EXPECTED_BLE_PEERS_LT_2' in text:
    raise SystemExit("stale EXPECTED_BLE_PEERS_LT_2 remains in native source")

NATIVE.write_text(text)
if not args.no_release_trigger:
    TRIGGER.write_text(
        "dev-15 two-device preflight hotfix " + datetime.now(timezone.utc).isoformat() + "\n"
    )
print("DEV15_TWO_DEVICE_PREFLIGHT_HOTFIX_APPLIED")
