#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one patch anchor, found {text.count(old)}")
    path.write_text(text.replace(old, new, 1))


def ensure_contains(path: Path, needle: str) -> None:
    if needle not in path.read_text():
        raise SystemExit(f"{path}: missing expected {needle!r}")

# Universal React Native app: do not put a multi-megabyte evidence JSON in Android EXTRA_TEXT.
app = ROOT / "apps/mobile/App.tsx"
replace_once(
    app,
    "    await Share.share({ message: JSON.stringify(payload, null, 2), title: suggestedFilename });",
    "    const serializedPayload = JSON.stringify(payload, null, 2);\n"
    "    if (Platform.OS === 'android') {\n"
    "      const shared = BodyFinderNative.shareJsonFile(serializedPayload, suggestedFilename);\n"
    "      if (!shared) throw new Error(lang === 'es' ? 'No se pudo preparar el archivo JSON para compartir.' : 'Could not prepare the JSON file for sharing.');\n"
    "    } else {\n"
    "      await Share.share({ message: serializedPayload, title: suggestedFilename });\n"
    "    }",
)

index = ROOT / "apps/mobile/modules/body-finder-native/index.ts"
replace_once(index, "  getDiagnosticsJson(): string;\n", "  getDiagnosticsJson(): string;\n  shareJsonFile(json: string, filename: string): boolean;\n")

module = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
replace_once(module, "import android.content.Context\nimport android.content.Intent\n", "import android.content.ClipData\nimport android.content.Context\nimport android.content.Intent\n")
replace_once(module, "import android.view.WindowManager\n", "import android.view.WindowManager\nimport androidx.core.content.FileProvider\n")
replace_once(module, "import java.net.DatagramPacket\n", "import java.io.File\nimport java.net.DatagramPacket\n")
share_function = '''    Function("shareJsonFile") { json: String, requestedFilename: String ->
      val ctx = appContext.reactContext ?: return@Function false
      val safeFilename = requestedFilename
        .replace(Regex("[^A-Za-z0-9._-]"), "_")
        .take(160)
        .let { if (it.endsWith(".json")) it else "$it.json" }
      val exportDir = File(ctx.cacheDir, "bodyfinder_exports").apply { mkdirs() }
      val file = File(exportDir, safeFilename)
      file.writeText(json, Charsets.UTF_8)
      val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.bodyfinder.fileprovider", file)
      val sendIntent = Intent(Intent.ACTION_SEND).apply {
        type = "application/json"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        clipData = ClipData.newRawUri(safeFilename, uri)
      }
      val chooser = Intent.createChooser(sendIntent, "Body Finder JSON").apply {
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      }
      ctx.startActivity(chooser)
      true
    }
'''
replace_once(module, '    Function("getCapabilitiesJson") {\n', share_function + '    Function("getCapabilitiesJson") {\n')

native_manifest = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/AndroidManifest.xml"
replace_once(
    native_manifest,
    "  <application>\n",
    "  <application>\n"
    "    <provider\n"
    "      android:name=\"androidx.core.content.FileProvider\"\n"
    "      android:authorities=\"${applicationId}.bodyfinder.fileprovider\"\n"
    "      android:exported=\"false\"\n"
    "      android:grantUriPermissions=\"true\">\n"
    "      <meta-data android:name=\"android.support.FILE_PROVIDER_PATHS\" android:resource=\"@xml/bodyfinder_file_paths\" />\n"
    "    </provider>\n",
)

native_gradle = ROOT / "apps/mobile/modules/body-finder-native/android/build.gradle"
if "androidx.core:core:" not in native_gradle.read_text():
    native_gradle.write_text(native_gradle.read_text() + "\ndependencies {\n  implementation 'androidx.core:core:1.16.0'\n}\n")

paths_xml = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/res/xml/bodyfinder_file_paths.xml"
paths_xml.parent.mkdir(parents=True, exist_ok=True)
paths_xml.write_text('''<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
  <cache-path name="bodyfinder_exports" path="bodyfinder_exports/" />
</paths>
''')

# Legacy APK: use the same file-based Android sharing contract.
legacy = ROOT / "apps/android-legacy/app/src/main/java/com/trochez/bodyfinderruview/legacy/MainActivity.java"
text = legacy.read_text()
if "FileProvider.getUriForFile" not in text:
    text = text.replace("import android.content.Context;import android.content.Intent;", "import android.content.ClipData;import android.content.Context;import android.content.Intent;", 1)
    text = text.replace("import android.widget.TextView;import org.json", "import android.widget.TextView;import androidx.core.content.FileProvider;import org.json", 1)
    text = text.replace("import java.net.DatagramPacket;", "import java.io.File;import java.net.DatagramPacket;", 1)
    pattern = r'private void shareSnapshot\(\)\{.*?\}\@Override protected void onDestroy'
    replacement = '''private void shareSnapshot(){try{String txt=new JSONObject().put("report_version",3).put("protocol_version",PROTOCOL).put("truth","LIVE_LEGACY_BLE_AND_WIFI_RSSI__AUTO_GEOMETRY_INPUT_ONLY").put("manual_geometry_override",false).put("advertisement",advertisement()).put("peer_count",peers.size()).toString(2);File dir=new File(getCacheDir(),"bodyfinder_exports");if(!dir.exists()&&!dir.mkdirs())throw new IllegalStateException("Cannot create export directory");File file=new File(dir,"body-finder-legacy-"+System.currentTimeMillis()+".json");java.io.FileOutputStream out=new java.io.FileOutputStream(file);out.write(txt.getBytes(StandardCharsets.UTF_8));out.close();android.net.Uri uri=FileProvider.getUriForFile(this,getPackageName()+".bodyfinder.fileprovider",file);Intent i=new Intent(Intent.ACTION_SEND);i.setType("application/json");i.putExtra(Intent.EXTRA_STREAM,uri);i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);i.setClipData(ClipData.newRawUri(file.getName(),uri));startActivity(Intent.createChooser(i,"Body Finder JSON"));}catch(Throwable t){status.setText("JSON export failed: "+String.valueOf(t));}}@Override protected void onDestroy'''
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit("legacy MainActivity: shareSnapshot patch anchor not found")
    legacy.write_text(text)

legacy_manifest = ROOT / "apps/android-legacy/app/src/main/AndroidManifest.xml"
replace_once(
    legacy_manifest,
    "        <activity android:name=\".MainActivity\"",
    "        <provider android:name=\"androidx.core.content.FileProvider\" android:authorities=\"${applicationId}.bodyfinder.fileprovider\" android:exported=\"false\" android:grantUriPermissions=\"true\">\n"
    "            <meta-data android:name=\"android.support.FILE_PROVIDER_PATHS\" android:resource=\"@xml/bodyfinder_file_paths\" />\n"
    "        </provider>\n"
    "        <activity android:name=\".MainActivity\"",
)
legacy_paths = ROOT / "apps/android-legacy/app/src/main/res/xml/bodyfinder_file_paths.xml"
legacy_paths.parent.mkdir(parents=True, exist_ok=True)
legacy_paths.write_text(paths_xml.read_text())
legacy_gradle = ROOT / "apps/android-legacy/app/build.gradle"
if "androidx.core:core:" not in legacy_gradle.read_text():
    legacy_gradle.write_text(legacy_gradle.read_text() + "\ndependencies { implementation 'androidx.core:core:1.16.0' }\n")
legacy_text = legacy_gradle.read_text().replace("versionCode 11; versionName '0.2.0-experimental.11'", "versionCode 12; versionName '0.2.0-experimental.20.1-legacy'")
legacy_gradle.write_text(legacy_text)

# Hotfix build identity; evidence schema/report version is intentionally unchanged.
version = ROOT / "apps/mobile/src/version.ts"
replace_once(version, "  build: '0.2.0-experimental.20',", "  build: '0.2.0-experimental.20.1',")
replace_once(version, "  versionCode: 20,", "  versionCode: 21,")
replace_once(version, "  releaseIteration: 'experimental.20',", "  releaseIteration: 'experimental.20.1',")
app_json = ROOT / "apps/mobile/app.json"
replace_once(app_json, '"versionCode": 20', '"versionCode": 21')
replace_once(app_json, '"releaseIteration": "experimental.20"', '"releaseIteration": "experimental.20.1"')

# Add a mandatory smoke check before users spend five minutes on each scenario.
doc = ROOT / "docs/TESTING_DEV20.md"
if "JSON share smoke test" not in doc.read_text():
    replace_once(
        doc,
        "## 2. Record runs\n",
        "## 2. JSON share smoke test\nBefore the full campaign, create a short diagnostic run (15-30 s) on each Android, end it, then tap **Share complete test JSON**. Android must open the system share chooser with a `.json` attachment. Save/share that file and confirm it parses as JSON. If the chooser or attachment does not appear, do not start the 5-minute campaign.\n\n## 3. Record runs\n",
    )
    text = doc.read_text().replace("## 3. Label externally", "## 4. Label externally").replace("## 4. Validate", "## 5. Validate").replace("## 5. Return evidence", "## 6. Return evidence")
    doc.write_text(text)

# Final contract checks before CI builds.
for p, n in [
    (app, "BodyFinderNative.shareJsonFile"),
    (module, "Intent.EXTRA_STREAM"),
    (module, "FileProvider.getUriForFile"),
    (native_manifest, "bodyfinder.fileprovider"),
    (legacy, "Intent.EXTRA_STREAM"),
    (legacy, "FileProvider.getUriForFile"),
    (legacy_manifest, "bodyfinder.fileprovider"),
]:
    ensure_contains(p, n)
print("DEV20_SHARE_HOTFIX_APPLIED")
