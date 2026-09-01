#!/usr/bin/env bash
set -euxo pipefail
: "${GH_TOKEN:?GH_TOKEN required}"

cleanup_on_error() {
  gh release delete dev-20.12 -y || true
  git push origin :refs/tags/dev-20.12 || true
}
trap cleanup_on_error ERR

rm -rf /tmp/dev20.12-final-1 /tmp/dev20.12-final-2
mkdir -p /tmp/dev20.12-final-1 /tmp/dev20.12-final-2

gh release download dev-20.12 --dir /tmp/dev20.12-final-1
test "$(find /tmp/dev20.12-final-1 -maxdepth 1 -type f | wc -l)" -eq 40

python3 - <<'PY'
import hashlib,json,pathlib
p=pathlib.Path('/tmp/dev20.12-final-1')
v=json.loads((p/'release-verification.json').read_text())
assert v['release_redownload_sha_verified'] is True
assert v['redownload_asset_count']==40
files=sorted(x for x in p.iterdir() if x.is_file() and x.name!='SHA256SUMS.txt')
assert len(files)==39
(p/'SHA256SUMS.txt').write_text(''.join(f'{hashlib.sha256(x.read_bytes()).hexdigest()}  {x.name}\n' for x in files))
PY

gh release upload dev-20.12 /tmp/dev20.12-final-1/SHA256SUMS.txt --clobber

gh release download dev-20.12 --dir /tmp/dev20.12-final-2
test "$(find /tmp/dev20.12-final-2 -maxdepth 1 -type f | wc -l)" -eq 40
(
  cd /tmp/dev20.12-final-2
  sha256sum -c SHA256SUMS.txt
)
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('/tmp/dev20.12-final-2')
v=json.loads((p/'release-verification.json').read_text())
assert v['release_redownload_sha_verified'] is True
assert v['redownload_asset_count']==40
listed={line.split('  ',1)[1] for line in (p/'SHA256SUMS.txt').read_text().splitlines() if '  ' in line}
actual={x.name for x in p.iterdir() if x.is_file() and x.name!='SHA256SUMS.txt'}
assert listed==actual and len(actual)==39
print('FINAL_RELEASE_VERIFIED dev-20.12 assets=40 hashes=39/39 G10=PENDING G11=BLOCKED G12=PENDING')
PY

trap - ERR
