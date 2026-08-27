# dev-19 final physical acceptance evidence

This directory records the final three-Android physical acceptance for `dev-19` / `0.2.0-experimental.19`.

Evidence set:

- `pixel10-dev19-final.json.gz` — lossless gzip of the complete Pixel 10 Pro JSON export
- `pixel7-dev19-final.json.gz` — lossless gzip of the complete Pixel 7 Pro JSON export
- `lenovo-dev19-final.json.gz` — lossless gzip of the complete Lenovo TB-J606L JSON export
- `dev19-3android-acceptance.json` — strict dev-19 validator result
- `dev19-final-acceptance.json` — final acquisition-baseline decision
- `SOURCE_RUNS.md` — exact run IDs and compressed-file integrity hashes

To recover an original JSON export:

```bash
gzip -dc pixel10-dev19-final.json.gz > pixel10-dev19-final.json
gzip -dc pixel7-dev19-final.json.gz > pixel7-dev19-final.json
gzip -dc lenovo-dev19-final.json.gz > lenovo-dev19-final.json
```

Decision:

- three-Android acceptance: `PASS`
- final acquisition-baseline GO: `true`
- human detection/localization/rescue remain outside dev-19 acceptance and are not claimed validated here.

The final decision is fail-closed: `final_go=true` only when the strict dev-19 validator reports overall PASS and all three device results PASS.
