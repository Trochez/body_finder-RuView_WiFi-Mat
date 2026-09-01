#!/usr/bin/env bash
set -euxo pipefail
: "${GH_TOKEN:?GH_TOKEN required}"
: "${SOURCE_SHA:?SOURCE_SHA required}"
mkdir -p dist work/deb/DEBIAN work/deb/usr/bin

# Linux runtime + detector.
tar -C target/release -czf dist/body-finder-node-linux-x86_64.tar.gz body-finder-node
cp target/release/body-finder-node work/deb/usr/bin/
printf 'Package: body-finder-node\nVersion: 0.2.0~experimental20.12\nSection: science\nPriority: optional\nArchitecture: amd64\nMaintainer: Trochez\nDescription: Body Finder RuView field node\n' > work/deb/DEBIAN/control
dpkg-deb --build work/deb dist/body-finder-node-linux-x86_64.deb
cp target/release/body-finder-detector dist/body-finder-detector-linux-x86_64
chmod +x dist/body-finder-detector-linux-x86_64

# Universal Android + AAB. Build Rust JNI for all release ABIs.
rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android
command -v cargo-ndk >/dev/null || cargo install cargo-ndk --locked
rm -rf apps/mobile/modules/body-finder-native/android/src/main/jniLibs
mkdir -p apps/mobile/modules/body-finder-native/android/src/main/jniLibs
cargo ndk -t arm64-v8a -t armeabi-v7a -t x86_64 -o apps/mobile/modules/body-finder-native/android/src/main/jniLibs build --release -p body-finder-science --lib
(
  cd apps/mobile
  ./android/gradlew -p android assembleRelease bundleRelease --stacktrace
)
cp apps/mobile/android/app/build/outputs/apk/release/*.apk dist/body-finder-ruview-universal.apk
cp dist/body-finder-ruview-universal.apk dist/BodyFinder-dev20.12-universal.apk
cp apps/mobile/android/app/build/outputs/bundle/release/*.aab dist/body-finder-ruview.aab

# Legacy minSdk21 APK.
mkdir -p "$HOME/.android"
if [ ! -f "$HOME/.android/debug.keystore" ]; then
  keytool -genkeypair -keystore "$HOME/.android/debug.keystore" -storepass android -alias androiddebugkey -keypass android -dname 'CN=Android Debug,O=Android,C=US' -keyalg RSA -keysize 2048 -validity 10000
fi
(
  cd apps/android-legacy
  gradle :app:testReleaseUnitTest :app:assembleRelease --stacktrace
)
cp apps/android-legacy/app/build/outputs/apk/release/*.apk dist/body-finder-ruview-legacy-minsdk21.apk

# Validators, fixtures, schemas, reports, testing instructions.
cp TESTING_DEV20_12.md dist/TESTING_DEV20_12.md
for f in dev20.12-evidence-schema-v15.json dev20.12-campaign-schema.json scenario-command-v1-schema.json run-start-v1-schema.json snapshot-freeze-v2-schema.json control-plane-v10-schema.json wire-transport-telemetry-v12-schema.json range-frame-v9-schema.json geometry-publication-v11-schema.json artifact-manifest-v4-schema.json; do cp validation/schemas/$f dist/$f; done
cp validation/detector-parameter-manifest-v9.json dist/detector-parameter-manifest-v9.json
for f in dev20.11-g10-no-go-verdict.json dev20.11-physical-evidence-root-cause-report.json critical-control-byte-budget-report.json authority-durability-report.json distributed-start-freeze-report.json artifact-v4-reliability-report.json export-safety-report.json multi-runtime-isolation-report.json transport-priority-report.json geometry-no-regression-report.json detector-v9-no-regression-report.json validator-contract-parity-report.json synthetic-dev20.12-g10-report.json release-manifest.json; do cp validation/reports/$f dist/$f; done
rm -rf kit fixturepack
mkdir -p kit/validation/analysis kit/validation/schemas kit/validation/reports fixturepack/dev20_12
cp validation/analysis/validate_dev20_12_preflight.py validation/analysis/validate_dev20_12_smoke.py validation/analysis/build_dev20_12_final_report.py validation/analysis/test_dev20_12_multi_runtime.py validation/analysis/test_dev20_12_contract.py kit/validation/analysis/
cp validation/schemas/dev20.12-evidence-schema-v15.json validation/schemas/dev20.12-campaign-schema.json validation/schemas/scenario-command-v1-schema.json validation/schemas/run-start-v1-schema.json validation/schemas/snapshot-freeze-v2-schema.json validation/schemas/control-plane-v10-schema.json validation/schemas/wire-transport-telemetry-v12-schema.json validation/schemas/range-frame-v9-schema.json validation/schemas/geometry-publication-v11-schema.json validation/schemas/artifact-manifest-v4-schema.json kit/validation/schemas/
cp validation/reports/*.json kit/validation/reports/
cp validation/detector-parameter-manifest-v9.json kit/validation/
cp TESTING_DEV20_12.md kit/
cp validation/reports/dev20.11-g10-no-go-verdict.json validation/reports/dev20.11-physical-evidence-root-cause-report.json validation/reports/synthetic-dev20.12-g10-report.json fixturepack/dev20_12/
printf '%s\n' 'Raw dev20.11 physical JSON fixtures were not versioned in baseline main@3fd11b673647afd1c0aac23907b34cb59ff78acd; this pack intentionally contains source-derived regression metadata and synthetic protocol fixtures only.' > fixturepack/dev20_12/RAW_FIXTURE_STATUS.txt
(cd kit && zip -qr ../dist/validators-dev20.12.zip .)
(cd fixturepack && zip -qr ../dist/fixtures-dev20.12.zip dev20_12)

# Release verification stays fail-closed for physical gates.
python3 - <<'PY'
import json,os,pathlib
p=pathlib.Path('dist/release-verification.json')
o={
 'schema_version':15,'release':'dev-20.12','build':'0.2.0-experimental.20.12','source_sha':os.environ['SOURCE_SHA'],
 'protocol_version':2,'report_version':32,'snapshot_schema_version':15,
 'evidence_contract':'dev20.12-self-contained-json-evidence-v15','wire_contract':'WireEnvelopeV10','wire_telemetry':'WireTransportTelemetryV12',
 'control_plane':'BodyFinderControlPlaneV10','artifact_manifest':'ArtifactManifestV4','geometry_publication':'GeometryPublicationV11',
 'detector_algorithm':'deterministic-multinode-rssi-fusion-v9','detector_parameter_hash':'f5795d40fbfb1de728b8576e214b249ada67f70d7962e1bf7794eb9c7d251f17',
 'engineering_ci_pass':True,'G10':'PENDING','G11':'BLOCKED','G12':'PENDING','g10_go':False,'g11_go':False,'g12_go':False,'final_go':False,'dev21_blocked':True,
 'screenshots_required':False,'raw_dev20_11_physical_fixtures_versioned':False,'release_redownload_sha_verified':False
}
p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
# Minimal valid SPDX 2.3 JSON SBOM with the release package itself as the root package.
sbom={'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0','SPDXID':'SPDXRef-DOCUMENT','name':'BodyFinder-dev20.12','documentNamespace':f'https://github.com/Trochez/body_finder-RuView_WiFi-Mat/releases/dev-20.12/{os.environ["SOURCE_SHA"]}','creationInfo':{'created':'2026-09-01T00:00:00Z','creators':['Tool: body-finder-release-dev20.12']},'packages':[{'SPDXID':'SPDXRef-Package','name':'body-finder-ruview','versionInfo':'0.2.0-experimental.20.12','downloadLocation':'NOASSERTION','filesAnalyzed':False,'licenseConcluded':'NOASSERTION','licenseDeclared':'NOASSERTION','copyrightText':'NOASSERTION'}],'relationships':[{'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES','relatedSpdxElement':'SPDXRef-Package'}]}
pathlib.Path('dist/SBOM.spdx.json').write_text(json.dumps(sbom,indent=2,sort_keys=True)+'\n')
PY

# Exact authoritative inventory: 39 assets before checksums, 40 after.
python3 - <<'PY'
import hashlib,pathlib
D=pathlib.Path('dist')
required='BodyFinder-dev20.12-universal.apk body-finder-ruview-universal.apk body-finder-ruview-legacy-minsdk21.apk body-finder-ruview.aab body-finder-node-linux-x86_64.tar.gz body-finder-node-linux-x86_64.deb body-finder-windows-wsl-x86_64.zip body-finder-detector-linux-x86_64 body-finder-detector-windows-x86_64.exe validators-dev20.12.zip fixtures-dev20.12.zip dev20.12-evidence-schema-v15.json dev20.12-campaign-schema.json scenario-command-v1-schema.json run-start-v1-schema.json snapshot-freeze-v2-schema.json control-plane-v10-schema.json wire-transport-telemetry-v12-schema.json range-frame-v9-schema.json geometry-publication-v11-schema.json artifact-manifest-v4-schema.json detector-parameter-manifest-v9.json dev20.11-g10-no-go-verdict.json dev20.11-physical-evidence-root-cause-report.json critical-control-byte-budget-report.json authority-durability-report.json distributed-start-freeze-report.json artifact-v4-reliability-report.json export-safety-report.json multi-runtime-isolation-report.json transport-priority-report.json geometry-no-regression-report.json detector-v9-no-regression-report.json validator-contract-parity-report.json synthetic-dev20.12-g10-report.json release-manifest.json release-verification.json SBOM.spdx.json TESTING_DEV20_12.md'.split()
actual=[p.name for p in D.iterdir() if p.is_file()]
missing=sorted(set(required)-set(actual));extra=sorted(set(actual)-set(required))
if missing or extra or len(actual)!=39: raise SystemExit(f'INVENTORY pre-SHA missing={missing} extra={extra} count={len(actual)}')
for n in required:
 if (D/n).stat().st_size<=0: raise SystemExit(f'EMPTY {n}')
files=sorted(p for p in D.iterdir() if p.is_file())
(D/'SHA256SUMS.txt').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in files))
assert len([p for p in D.iterdir() if p.is_file()])==40
PY

# Publish only after all engineering/build/inventory gates pass.
trap 'gh release delete dev-20.12 -y || true; git push origin :refs/tags/dev-20.12 || true' ERR
git tag -f dev-20.12 "$SOURCE_SHA"
git push origin refs/tags/dev-20.12 --force
gh release delete dev-20.12 -y || true
gh release create dev-20.12 dist/* --prerelease --target "$SOURCE_SHA" --title 'Release dev-20.12 — distributed authority/artifact remediation' --notes 'Engineering gates PASS. G10=PENDING, G11=BLOCKED, G12=PENDING, final_go=false, dev21_blocked=true. Raw dev20.11 physical JSON fixtures were not versioned; this limitation is explicit in the fixture package. Follow TESTING_DEV20_12.md. No screenshots required.'
rm -rf redownload && mkdir redownload
gh release download dev-20.12 --dir redownload
test "$(find redownload -maxdepth 1 -type f | wc -l)" -eq 40
(cd redownload && sha256sum -c SHA256SUMS.txt)
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('redownload/release-verification.json');o=json.loads(p.read_text());o['release_redownload_sha_verified']=True;o['redownload_asset_count']=40;pathlib.Path('/tmp/release-verification.json').write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
PY
gh release upload dev-20.12 /tmp/release-verification.json#release-verification.json --clobber
rm -rf verify2 && mkdir verify2
gh release download dev-20.12 --dir verify2
test "$(find verify2 -maxdepth 1 -type f | wc -l)" -eq 40
python3 - <<'PY'
import json,pathlib
v=json.loads(pathlib.Path('verify2/release-verification.json').read_text());assert v['release_redownload_sha_verified'] is True and v['redownload_asset_count']==40
print('RELEASE_VERIFIED dev-20.12 assets=40 G10=PENDING G11=BLOCKED G12=PENDING')
PY
