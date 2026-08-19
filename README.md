# Body Finder – RuView

Offline, multi-device experimental RF sensing and relative-position research application inspired by and designed to interoperate with RuView/WiFi-Mat.

## Current truth status

**This repository does not claim validated human localization through walls or rubble.** The current implementation is a physical-validation stack for Android + Ubuntu/WSL/Windows, plus iOS build validation. It records provenance and explicit uncertainty and never labels RSSI as CSI.

## Automatic sensor geometry — protocol v2

The normal operator flow requires **no manual X/Y/Z sensor coordinates**. Nodes discover peers, publish real pairwise range observations when a verified runtime adapter can produce them, and solve a relative 1D/2D sensor frame automatically. Missing, disconnected or degenerate measurement graphs remain `GEOMETRY_INSUFFICIENT`/`GEOMETRY_DEGRADED`; unresolved nodes are not placed at default coordinates.

Current live Android pairwise fallback is BLE advertisement RSSI with deliberately conservative uncertainty. Android API-36 ranging and Wi-Fi RTT are capability-probed but are not presented as live precision ranging until an actual ranging session produces measurements. Connected Wi-Fi RSSI remains a separate experimental human-presence signal and is never used as direct phone-to-phone distance.

See [IMPLEMENTATION_PLAN_AUTOGEOMETRY_RELEASE.md](IMPLEMENTATION_PLAN_AUTOGEOMETRY_RELEASE.md) and [docs/TESTING_AUTOGEOMETRY_RELEASE.md](docs/TESTING_AUTOGEOMETRY_RELEASE.md).

## Components

- `crates/body-finder-core` — protocol v2, automatic geometry solver, uncertainty, coordinator election and experimental human fusion.
- `apps/node` — Ubuntu/WSL/Windows native Rust node; no normal `--x/--y` arguments.
- `apps/mobile` — Android/iOS React Native UI; Android native adapter provides live BLE range observations when available.
- `apps/android-legacy` — minSdk21 Android fallback node with no manual coordinates.
- `validation` — ground-truth template, fixtures and automatic result validator.
- `upstream/ruvieW.lock.json` — exact reviewed RuView snapshot.

## Development

```bash
cargo test --workspace
cargo run -p body-finder-node -- --node ubuntu-a --calibrate 10 --record ubuntu-a.jsonl

cd apps/mobile
npm install
npx tsc --noEmit
npx expo prebuild --platform android
```

## Safety

A negative RF scan is never proof that no person is present. Do not use experimental builds as rescue equipment and never test in an unstable structure.
