# DEV17 Event ↔ Frozen Counter Mapping

Acceptance truth is reconstructed only from `validation_run.events`; top-level live diagnostics are never substitutes for a completed run.

| Frozen field | Event reconstruction |
|---|---|
| `validation_counters.recovery_attempt_delta` | count `RECOVERY_REQUESTED` |
| `validation_counters.recovery_first_valid_callback_delta` | count `FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY` |
| `peer_starvation_recovery_request_delta` | `RECOVERY_REQUESTED(trigger_kind=PEER_STARVATION)` |
| `peer_starvation_recovery_success_delta` | matching `RECOVERY_SUCCESS` |
| `peer_starvation_recovery_failure_delta` | matching `RECOVERY_FAILURE` |
| per-peer `run_starvation_recovery_participation_count` | targeted requests owned by `trigger_peer_id` |
| per-peer `run_first_callback_after_recovery_count` | FIRST_VALID where `peer_id == trigger_peer_id` |
| per-peer `run_starvation_recovery_success_count` | targeted successes on that peer |
| per-peer `run_starvation_recovery_failure_count` | targeted failures on that peer |
| `recovery_attempt_delta_total` | total request events |
| `recovery_attempts_in_current_5min_window_at_end` | requests in `[ended_wall_ms-300000, ended_wall_ms]` |
| `recovery_attempts_max_in_any_rolling_5min_window` | maximum requests in any inclusive rolling 300000 ms window |
| `generation_count` | recovery generations containing one request |
| `max_unfiltered_duration_ms` | max request→terminal duration |
| `unfiltered_action_target_miss_count` | request→terminal `>9500 ms` |
| `unfiltered_hard_limit_breach_count` | request→terminal `>10000 ms` |
| `max_filtered_probe_duration_ms` | max enter-probe→leave-probe duration |
| `filtered_probe_target_miss_count` | probe duration `>14500 ms` |
| `filtered_probe_hard_limit_breach_count` | probe duration `>15000 ms` |

A targeted successful generation must be exactly `REQUESTED < FIRST_VALID(target) < SUCCESS(target)`. Exactly one terminal is allowed. Reexports are deduplicated by `(device identity, run_id, recovery_generation)`.
