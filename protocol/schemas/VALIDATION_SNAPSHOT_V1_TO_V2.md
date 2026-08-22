# Validation snapshot v1 → v2

v2 preserves the v1 run counters and adds bounded completed-run history, explicit selected-run export, recovery generations, canonical lifetime/run/recovery peer telemetry, and frozen geometry/fusion/graph truth at End. v1 readers may continue consuming legacy flat counters; v2 readers must prefer `per_peer_at_end` and the `*_at_end` geometry fields.
