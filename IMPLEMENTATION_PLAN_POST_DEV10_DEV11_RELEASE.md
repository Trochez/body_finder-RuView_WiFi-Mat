# IMPLEMENTATION_PLAN_POST_DEV10_DEV11_RELEASE.md

## Objetivo

Cerrar los pendientes posteriores a la campaña física de `dev-10` y producir `dev-11` como release reproducible, auditable y completamente testeable, preservando sin cambios la física BLE validada en `dev-9/dev-10`.

El alcance de `dev-11` es exclusivamente: integridad e historial de snapshots; provenance/timeline causal; semántica per-peer lifetime/run/recovery; freeze de geometría/fusión/graph al End; versión/UI/export consistentes; contratos/regresiones automáticos; CI multi-plataforma; release verificable; e instructivo final de aceptación con 3 Androids.

## Defectos de entrada confirmados

1. Un nuevo Validation Run puede reemplazar el último completed snapshot exportable.
2. `BF_COHORT_STALLED` puede registrarse después de `RECOVERY_REQUESTED`.
3. `BF_COHORT_STALLED` puede exportar `cohort_health=BF_COHORT_HEALTHY`.
4. Puede haber más de un `FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY` por recovery.
5. `peer_recovery_count` mezcla gaps >5 s con recoveries reales.
6. Métricas per-peer lifetime y run-scoped no están claramente separadas.
7. Geometría/fusión/graph diagnostics no quedan congelados completamente al End.
8. Existe texto UI stale de `experimental.9`.
9. Faltan contratos automáticos para estas invariantes.
10. Precisión física permanece `COARSE`; no se recalibra en dev-11.

## Frozen truth — NO modificar

```text
profile_id                    = android-ble-lab-v1
RSSI @ 1 m                    = -69.19 dBm
path-loss exponent n          = 3.62
validated distance domain     = 0.5–5.0 m
minSamples                    = 3
fresh                         = 5 s
holdover / hard expiry        = 10 s
sigma aging                   = 0.15 m/s
primary acquisition           = FILTERED_PRIMARY
recovery acquisition          = UNFILTERED_RECOVERY
cohort stall threshold        = 5 s
unfiltered recovery window    = 10 s
filtered recovery probe       = 15 s
restart cooldown              = 30 s
max recoveries / rolling 5m   = 3
Android API36 BLE yield       = 120 s
protocol version              = 2
human scanning                = false
human localization validated  = false
rescue use validated          = false
```

Prohibido recalibrar RSSI, alterar holdover, cambiar solver, relajar gates, habilitar human scanning o declarar rescue validation.

## Versiones dev-11

```text
version                 = 0.2.0-experimental.11
report_version          = 13
versionCode             = 11
releaseIteration        = experimental.11
snapshot_schema_version = 2
MAX_COMPLETED_VALIDATION_RUNS = 5
```

## Arquitectura objetivo

`CompletedValidationRun` debe ser inmutable y contener al menos:

```text
snapshot_schema_version
run_id
started_wall_ms
ended_wall_ms
elapsed_ms
snapshot_frozen
environment
validation_counters
acquisition_state_at_end
per_peer_at_end
system_ranging_at_end
events
geometry_at_end
locally_computed_geometry_at_end
fused_range_observations_at_end
graph_diagnostics_at_end
reciprocal_fusion_at_end
measurement_health_at_end
```

El historial conserva los últimos 5 completed runs mediante FIFO. `Start N+1` no borra N. El export contiene `selected_validation_run_id`, `validation_run` y `completed_validation_runs_summary`; por defecto se selecciona el latest completed run y la UI permite seleccionar históricos.

## Recovery causal

Cada recovery usa `recovery_generation` Long monotónico. Orden esperado:

```text
BF_COHORT_STALLED
  -> RECOVERY_REQUESTED
  -> ACQUISITION_STRATEGY_CHANGED: UNFILTERED_RECOVERY
  -> FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY
  -> RECOVERY_SUCCESS
  -> FILTERED_RECOVERY_PROBE
  -> FILTERED_PRIMARY
```

Invariantes: `seq` creciente; `wall_ms` y `elapsed_ms` no decrecientes; STALL exporta estado STALLED; máximo un FIRST_VALID por generation; SUCCESS requiere generation activo; request nunca precede al stall causal; eventos de una transición reutilizan el mismo `now`.

## Semántica per-peer

Lifetime:

```text
lifetime_callback_count
lifetime_gap_gt_1s_count
lifetime_gap_gt_2s_count
lifetime_gap_gt_5s_count
lifetime_gap_gt_10s_count
```

Run-scoped:

```text
run_callback_delta
run_valid_callback_delta
run_invalid_callback_delta
run_gap_gt_1s_delta
run_gap_gt_2s_delta
run_gap_gt_5s_delta
run_gap_gt_10s_delta
run_filtered_callback_delta
run_unfiltered_callback_delta
```

Recovery real:

```text
run_recovery_participation_count
run_first_callback_after_recovery_count
last_recovery_generation_seen
last_recovery_callback_latency_ms
```

No se permite inferir recovery a partir de `gap_gt_5s_count`.

## Backlog ejecutable

1. Freeze de arquitectura/versiones/RF/safety truth.
2. Corregir timeline causal, generation e idempotencia recovery.
3. Implementar bounded immutable completed-run history y selección de export.
4. Separar lifetime/run/recovery telemetry.
5. Congelar geometry/fusion/graph/measurement truth al End.
6. Centralizar version truth y corregir UI; mostrar historial/selección.
7. Crear schema v2, fixtures positivos/negativos, comparators y contract tests.
8. Crear CI `ci-exp11.yml` con requirements, Android, Android legacy, Linux, Windows e iOS Simulator.
9. Crear release pipeline `release-exp11.yml`, SBOM, checksums, manifest y assets.
10. Crear self-verifier de release publicado.
11. Crear `ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md` para la campaña física de 3 Androids.

## Gates obligatorios

- G1 Version truth: `0.2.0-experimental.11`, report 13, versionCode 11, releaseIteration exp11; ningún literal runtime/UI exp9/exp10.
- G2 RF truth frozen exactamente.
- G3 Run A sigue disponible después de Start B.
- G4 Completed snapshot inmutable entre exports.
- G5 `seq`, `wall_ms`, `elapsed_ms` monotónicos.
- G6 Stall causalmente anterior a request por generation.
- G7 máximo un FIRST_VALID por generation.
- G8 STALL implica `cohort_health=BF_COHORT_STALLED`.
- G9 Lifetime/run/recovery telemetry semánticamente separada.
- G10 geometry/fusion/graph-at-End inmutables.
- G11 human scanning/localization/rescue permanecen false.

## CI matrix requerida

```text
requirements/contracts   PASS
Android universal        PASS
Android legacy           PASS
Linux x86_64             PASS
Windows x86_64           PASS
iOS Simulator            PASS
artifact assertion       PASS
SBOM generation          PASS
checksum verification    PASS
published release verifier PASS
```

## Artefactos obligatorios

```text
body-finder-ruview-universal.apk
body-finder-ruview.aab
body-finder-ruview-legacy-minsdk21.apk
body-finder-node-linux-x86_64.tar.gz
body-finder-node-linux-x86_64.deb
body-finder-node-windows-x86_64.zip
body-finder-ruview-ios-simulator.zip
ANDROID_DEV11_FINAL_ACCEPTANCE_RETEST.md
IMPLEMENTATION_PLAN_POST_DEV10_DEV11_RELEASE.md
validation-run-snapshot-v2.schema.json
validation-snapshot-v2-regression-fixtures.zip
recovery-timeline-regression-fixtures.zip
peer-telemetry-regression-fixtures.zip
geometry-at-end-regression-fixtures.zip
body-finder-validation-tools.zip
release-manifest.json
capability-matrix.json
ble-range-calibration-profiles.json
ble-range-calibration-schema.json
protocol-version.txt
model-manifest.json
ruview-upstream-lock.json
SBOM.spdx.json
SHA256SUMS
release-verification.json
```

## Acceptance física final

Dispositivos: Pixel 10 Pro, Pixel 7 Pro, Lenovo TB-J606L. Bluetooth ON, Battery Saver OFF, screen ON, app foreground, misma sesión; Lenovo Location ON. Triángulo no colineal, cada par 0.5–5 m. Warm-up 30 s y verificar 3 nodes/2 BLE peers/FILTERED_PRIMARY/MANUFACTURER_FILTERED/hardware filter >0/environment_valid.

Run principal: Start en los 3, >=5 min sin movimiento, End, `snapshot_frozen=true`; export #1; mantener runtime >=3 min; export #2 del mismo `run_id`; iniciar/terminar un short run; volver al long run histórico; exportarlo y comprobar identidad.

Hard gates por dispositivo:

```text
snapshot_frozen = true
elapsed_ms >= 300000
usable_metric_range_uptime_percent >= 90
geometry_2d_uptime_percent >= 90
peer_expire_delta = 0
recovery_attempt_delta <= 3
environment_valid = true
```

Además: timeline monotónico/causal, STALL state truth, one-first-callback/generation, history preservation, peer semantics correctas y geometry-at-End inmutable.

Accuracy report usa ground truth externo sin introducirlo a la app y reporta directional MAE, reciprocal fused MAE, worst absolute error y uncertainty coverage. Sigue siendo informativo bajo `physical_confidence=COARSE` y no bloquea dev-11 por recalibración.

## Definition of Done

`dev-11` sólo está listo cuando CI matrix y published-release verifier están PASS y el release contiene todos los assets anteriores. La **aceptación física** sólo puede declararse PASS después de ejecutar la campaña real con los 3 Androids; publicar dev-11 no equivale a afirmar que dicha campaña ya fue ejecutada.

Incluso con PASS: `human_scanning_enabled=false`, `human_localization_validated=false`, `rescue_use_validated=false`.
