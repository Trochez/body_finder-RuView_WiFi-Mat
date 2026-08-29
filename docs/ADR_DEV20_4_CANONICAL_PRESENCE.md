# ADR — dev-20.4 canonical presence

One authoritative detector exists: `body-finder-science::human_detector`. Android invokes its Rust `cdylib` through JNI; Linux/Windows validators invoke the same crate through `body-finder-detector`. TypeScript only ingests samples, assigns **local receive wall time**, owns coordinator/calibration orchestration, and transports the immutable canonical result. Source monotonic timestamps are provenance only and are never compared across devices or against wall time.

Calibration is coordinator-owned and stateful (`UNCALIBRATED → CALIBRATING → READY`, otherwise `INVALID`). It freezes six directional-link robust baselines under one calibration ID/hash. Any topology or detector-hash change invalidates it. Missing topology, comparable time, calibration, environment health, or parameter parity fails closed as `INDETERMINATE`.

Physical acceptance remains pending until the 6-JSON smoke and subsequent fresh 54-JSON TEST succeed.
