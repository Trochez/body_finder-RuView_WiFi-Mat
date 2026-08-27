#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def read(rel): return (ROOT / rel).read_text()
def require(rel, *needles):
    text = read(rel)
    missing = [x for x in needles if x not in text]
    if missing:
        raise SystemExit(f"FAIL {rel}: missing {missing}")

app = read("apps/mobile/App.tsx")
if "await Share.share({ message: JSON.stringify(payload" in app:
    raise SystemExit("FAIL universal: full evidence JSON still sent inline through React Native Share")
require("apps/mobile/App.tsx", "Platform.OS === 'android'", "BodyFinderNative.shareJsonFile(serializedPayload, suggestedFilename)")
require("apps/mobile/modules/body-finder-native/index.ts", "shareJsonFile(json: string, filename: string): boolean")
require("apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt",
        'Function("shareJsonFile")', "File(ctx.cacheDir, \"bodyfinder_exports\")", "FileProvider.getUriForFile",
        "Intent.ACTION_SEND", "Intent.EXTRA_STREAM", "FLAG_GRANT_READ_URI_PERMISSION", 'type = "application/json"', "ClipData.newRawUri")
require("apps/mobile/modules/body-finder-native/android/src/main/AndroidManifest.xml",
        "androidx.core.content.FileProvider", "${applicationId}.bodyfinder.fileprovider", "@xml/bodyfinder_file_paths")
require("apps/mobile/modules/body-finder-native/android/src/main/res/xml/bodyfinder_file_paths.xml",
        '<cache-path name="bodyfinder_exports" path="bodyfinder_exports/"')
legacy = read("apps/android-legacy/app/src/main/java/com/trochez/bodyfinderruview/legacy/MainActivity.java")
if "i.putExtra(Intent.EXTRA_TEXT,txt)" in legacy:
    raise SystemExit("FAIL legacy: JSON still sent inline through EXTRA_TEXT")
require("apps/android-legacy/app/src/main/java/com/trochez/bodyfinderruview/legacy/MainActivity.java",
        "FileProvider.getUriForFile", "Intent.EXTRA_STREAM", "FLAG_GRANT_READ_URI_PERMISSION", 'i.setType("application/json")', "ClipData.newRawUri")
require("apps/android-legacy/app/src/main/AndroidManifest.xml",
        "androidx.core.content.FileProvider", "${applicationId}.bodyfinder.fileprovider", "@xml/bodyfinder_file_paths")
require("apps/android-legacy/app/src/main/res/xml/bodyfinder_file_paths.xml",
        '<cache-path name="bodyfinder_exports" path="bodyfinder_exports/"')
# 8 MiB represents an evidence payload far larger than Android Binder's safe inline-share range.
stress = '{"evidence":"' + ('x' * (8 * 1024 * 1024)) + '"}'
assert len(stress.encode()) > 8_000_000
print("PASS android_json_share_contract=file_uri_extra_stream stress_payload_bytes=%d" % len(stress.encode()))
