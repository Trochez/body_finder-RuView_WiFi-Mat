# Source runs

- Pixel 10 Pro: `f9fd6431-85ca-4e0f-a8b1-9c7676b034e5`
- Pixel 7 Pro: `886acc56-e3ab-4d14-b4be-cf337ee914b5`
- Lenovo TB-J606L: `20befcc5-1b84-4e5b-a391-213fc848dce3`

The complete source exports are preserved losslessly in this branch as gzip files:

- `pixel10-dev19-final.json.gz` — SHA-256 `f79f99cd97706937d806cfe1c17d9b591f9347c63e09dcabb86068bda33eec88`
- `pixel7-dev19-final.json.gz` — SHA-256 `6335572628b6f4658ac1e5ba16fe4419cab2650c11f3fbc66054609f261886bd`
- `lenovo-dev19-final.json.gz` — SHA-256 `261afa0afb40f32fbc6c4e86a9b0fee09a25bc8da5ce3bc6caa6d234643f3e14`

Use `gzip -dc <file>.json.gz > <file>.json` to recover the exact JSON content used as physical evidence.
