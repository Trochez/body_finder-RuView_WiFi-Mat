# Body Finder – RuView

Offline, multi-device experimental RF sensing and relative-position research application inspired by and designed to interoperate with RuView/WiFi-Mat.

## Current truth status

**This repository does not yet claim validated human localization through walls or rubble.** The first release is an instrumented physical-validation build for Android + Ubuntu/WSL/Windows. It uses real OS-exposed Wi-Fi RSSI when available, never labels RSSI as CSI, records provenance, and shows explicit localization uncertainty.

The common-device baseline is intentionally simple and auditable: after an empty-scene calibration, 3+ positioned nodes contribute calibrated RSSI disturbance. The current experimental estimator computes a weighted 2D hypothesis and a deliberately inflated 95% uncertainty region. Only ground-truth field trials can determine whether this signal is useful in a specific layout.

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the product contract and [docs/TESTING_DEV_RELEASE.md](docs/TESTING_DEV_RELEASE.md) for the physical test protocol.

## Components

- `crates/body-finder-core` — protocol, coordinator election, experimental localization, uncertainty/provenance.
- `apps/node` — native Rust node for Ubuntu, WSL and Windows; reads live Wi-Fi metrics where exposed, discovers peers over UDP and records JSONL.
- `apps/mobile` — Expo/React Native Android app with native Kotlin capability/RSSI/fabric adapter and Radar/Expert UI.
- `upstream/ruvieW.lock.json` — exact RuView snapshot reviewed by the project.

## Development

```bash
cargo test --workspace
cargo run -p body-finder-node -- --node ubuntu-a --x 0 --y 0 --calibrate 10 --record ubuntu-a.jsonl

cd apps/mobile
npm install
npx expo prebuild --platform android
npx expo run:android
```

## Safety

A negative RF scan does **not** prove that no person is present. Do not use experimental builds as a replacement for trained search-and-rescue procedures or validated sensing equipment.
