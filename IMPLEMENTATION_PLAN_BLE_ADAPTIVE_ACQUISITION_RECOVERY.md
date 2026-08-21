# Body Finder – RuView
# Plan de implementación para recuperación adaptativa de adquisición BLE Body Finder

> **Repositorio objetivo:** `Trochez/body_finder-RuView_WiFi-Mat`  
> **Baseline:** `dev-8` / `0.2.0-experimental.8`  
> **Release objetivo recomendado:** `0.2.0-experimental.9`  
> **Protocol version objetivo:** `2`  
> **Estado:** READY FOR IMPLEMENTATION  
> **Objetivo:** resolver el stall específico del cohort Body Finder observado en Pixel 7 Pro y Pixel 10 Pro sin relajar la validez física, la calibración BLE, los límites temporales, reciprocal fusion ni el solver.

---

# 0. Resumen ejecutivo

La prueba física de `experimental.8` aisló un nuevo cuello de botella.

La arquitectura general funciona:

```text
UDP fabric                     PASS
peer discovery                 PASS
foreground service             PASS
wake / Wi-Fi / multicast lock  PASS
peer expiry                    PASS
BLE transmit                   PASS
BLE calibration                PASS
distance estimator             PASS
RSSI 127 sanitation            PASS
bounded holdover               PASS
RangingManager BLE yield       PASS
```

Sin embargo, en Pixel 7 Pro y Pixel 10 Pro ocurrió este patrón:

```text
generic BLE callbacks continúan
        ↓
scanner Android parece vivo
        ↓
Body Finder advertisements dejan de llegar
        ↓
last_any_scan_result_age pequeño
last_body_finder_scan_result_age enorme
        ↓
scan_callback_health = SCANNER_HEALTHY   ← incorrecto
        ↓
no recovery específica
        ↓
fresh metric colapsa
        ↓
holdover expira
        ↓
Geometry 2D colapsa
```

Mientras tanto, Lenovo continuó recibiendo correctamente advertisements provenientes de Pixel 7 y Pixel 10, lo que indica que el problema no es primariamente de transmisión.

La estrategia `LOW_LATENCY + ALL_MATCHES + software filtering` usada como modo primario en `experimental.8` produjo una regresión fuerte en los Pixels.

Por tanto, `experimental.9` debe:

```text
1. volver a manufacturer-filtered LOW_LATENCY como modo primario;
2. distinguir global scanner health de Body Finder cohort health;
3. detectar BODY_FINDER_COHORT_STALLED;
4. ejecutar recovery controlado;
5. usar ALL_MATCHES software-filtered solo como fallback temporal;
6. regresar al modo filtrado cuando el cohort se recupera;
7. aplicar hysteresis/cooldown para evitar restart thrashing;
8. exportar strategy transitions y recovery latency;
9. impedir una validation run si Battery Saver está ON;
10. mantener todos los parámetros físicos congelados.
```

---

# 1. Hallazgos de `dev-8` que este plan debe cubrir

## H-01 — Strategy regression

`experimental.8` usó:

```text
LOW_LATENCY
ALL_MATCHES
hardware_filter_count = 0
software Body Finder filtering
```

y la continuidad empeoró en los Pixels.

**Estado:** OPEN / P0.

## H-02 — Body Finder cohort stall invisible

Ejemplo conceptual observado:

```text
last_any_scan_result_age_ms        ≈ decenas de ms
last_body_finder_scan_result_age_ms ≈ cientos de segundos
scan_callback_health               = SCANNER_HEALTHY
```

La salud global del scanner no representa la salud de adquisición Body Finder.

**Estado:** OPEN / P0.

## H-03 — Pixel receivers pierden el cohort completo

Pixel 7 y Pixel 10 dejaron de recibir simultáneamente ambos peers Body Finder durante la corrida, mientras seguían llegando callbacks BLE de terceros.

**Estado:** OPEN / P0.

## H-04 — Lenovo demuestra que los transmitters siguen vivos

Lenovo recibió anuncios de Pixel 7 y Pixel 10 a varios Hz durante el mismo periodo.

**Estado:** CLOSED como hipótesis de TX global.

## H-05 — Restart counters altos fuera del run

Se observaron acumulaciones del orden de:

```text
Pixel7  scan_restart_count ~130
Pixel10 scan_restart_count ~126
Lenovo  scan_restart_count = 0
```

aunque `scan_restart_delta=0` durante la corrida.

Esto indica historial de thrashing o inestabilidad previa del scanner.

**Estado:** OPEN / P0.

## H-06 — Battery Saver contaminó Pixel10

Pixel 10 reportó:

```text
power_save_mode = true
```

durante una prueba que exigía Battery Saver OFF.

**Estado:** OPEN / P0 para validación ambiental.

## H-07 — RangingManager yield sí funcionó

Pixel 10 entró correctamente en:

```text
BLE_ACQUISITION_YIELD
```

tras múltiples cierres sin distancia real.

**Estado:** CLOSED / mantener sin cambios.

---

# 2. Invariantes físicos congelados

`experimental.9` NO puede modificar:

```text
profile_id = android-ble-lab-v1
RSSI@1m = -69.19 dBm
path_loss_exponent n = 3.62

validated = true

valid_distance_min_m = 0.5
valid_distance_max_m = 5.0

physical_confidence = COARSE

minimum_valid_samples = 3

fresh_ms = 5000
holdover_max_ms = 10000
hard_expiry_ms = 10000

sigma_aging_m_per_s = 0.15

reciprocal fusion semantics
reciprocal disagreement gating
metric graph rules
solver rules
```

También queda prohibido:

```text
aumentar holdover para inflar uptime
bajar minSamples 3→1
ampliar el dominio 0.5–5 m
reintroducir silent clamp
permitir RSSI 127 en valid queue
subir physical_confidence
habilitar human scanning
```

---

# 3. Principio arquitectónico central

El sistema debe separar claramente:

```text
GLOBAL BLE SCANNER HEALTH
        ≠
BODY FINDER COHORT ACQUISITION HEALTH
```

Un scanner puede seguir recibiendo BLE de terceros y, al mismo tiempo, haber perdido por completo todos los advertisements Body Finder relevantes.

El recovery debe reaccionar al segundo estado, no únicamente al primero.

---

# 4. Tamaño del equipo

## 4.1 Tamaño recomendado

**8 miembros lógicos**.

```text
1 Tech Lead / Solution Architect
1 Android BLE Platform Engineer
1 RF / Acquisition Reliability Engineer
1 Protocol & State-Machine Engineer
1 Mobile UX / Diagnostics Engineer
1 QA / Test Automation Engineer
1 DevOps / Release Engineer
1 Field Validation Engineer
```

Este incremento requiere un especialista adicional de plataforma Android porque el problema está específicamente en comportamiento BLE por dispositivo/stack.

## 4.2 Tamaño mínimo viable

**4 personas**, combinando:

```text
TL + Protocol/State Machine
Android BLE + RF Reliability
Mobile UX + QA
DevOps + Field Validation
```

## 4.3 Tamaño máximo recomendado

**9 personas**.

Más de 9 incrementaría el coste de coordinación para un problema fuertemente acoplado.

---

# 5. Roles

## TL — Tech Lead / Solution Architect

Responsable de:

- mantener invariantes físicos;
- definir estrategia adaptativa;
- aprobar state machine;
- aprobar thresholds;
- autorizar merge;
- bloquear human scanning.

## ABP — Android BLE Platform Engineer

Responsable de:

- ScanSettings;
- ScanFilter;
- start/stop/restart scanner;
- fallback entre modos;
- callbacks Android;
- device-specific runtime telemetry;
- coexistencia con RangingManager.

## RAR — RF / Acquisition Reliability Engineer

Responsable de:

- thresholds de cohort stall;
- hysteresis;
- cooldown;
- recovery latency;
- gap distributions;
- análisis de seis direcciones.

## PSM — Protocol & State-Machine Engineer

Responsable de:

- acquisition strategy states;
- cohort-health states;
- transition provenance;
- export protocol;
- validation-run counters.

## MUD — Mobile UX / Diagnostics Engineer

Responsable de:

- Expert;
- Radar;
- environment validation;
- strategy badges;
- cohort stall diagnostics;
- export UX.

## QAE — QA / Test Automation Engineer

Responsable de:

- timeline fixtures;
- strategy transition tests;
- regression dev-7/dev-8;
- Battery Saver tests;
- no-thrashing tests;
- release gates.

## DRE — DevOps / Release Engineer

Responsable de:

- CI;
- release contracts;
- artifact matrix;
- release manifest;
- SBOM;
- SHA256;
- prerelease publication.

## FVE — Field Validation Engineer

Responsable de:

- 3-device retest;
- environment control;
- evidence collection;
- timing;
- screenshots;
- package naming.

---

# 6. RACI

| Dominio | A | R | C | I |
|---|---|---|---|---|
| Primary scan strategy | TL | ABP | RAR, QAE | PSM |
| Cohort stall detection | TL | RAR | ABP, PSM | MUD |
| Adaptive state machine | TL | PSM | ABP, RAR | QAE |
| Scanner recovery | TL | ABP | RAR | DRE |
| Hysteresis/cooldown | TL | RAR | ABP | QAE |
| Battery Saver gate | TL | MUD | ABP, QAE | FVE |
| Diagnostics/export | TL | MUD | PSM, RAR | QAE |
| Tests | QAE | QAE | todos | TL |
| Release | TL | DRE | QAE | todos |
| Physical retest | TL | FVE | RAR, QAE | todos |

---

# 7. Acquisition strategy states

Definir:

```text
FILTERED_PRIMARY
UNFILTERED_RECOVERY
FILTERED_RECOVERY_PROBE
COOLDOWN
FAILED_SAFE
```

## 7.1 FILTERED_PRIMARY

Modo normal:

```text
SCAN_MODE_LOW_LATENCY

manufacturer Body Finder ScanFilter
reportDelay = 0

API >= 23:
MATCH_MODE_AGGRESSIVE
MATCH_NUM_MAX_ADVERTISEMENT
```

Objetivo:

- aprovechar filtering/offload nativo;
- reducir ruido de callbacks irrelevantes;
- volver al comportamiento que fue mejor en `experimental.7`.

## 7.2 UNFILTERED_RECOVERY

Solo cuando se detecta un stall de cohort.

```text
ALL_MATCHES
hardware_filter_count = 0
software validation Body Finder
```

Duración limitada.

No puede convertirse nuevamente en modo permanente.

## 7.3 FILTERED_RECOVERY_PROBE

Después de recuperación:

- volver temporalmente a filtered;
- verificar que los peers continúan apareciendo;
- si se mantienen, regresar a `FILTERED_PRIMARY`.

## 7.4 COOLDOWN

Evita alternar/reiniciar repetidamente.

## 7.5 FAILED_SAFE

Si el recovery excede límites:

```text
acquisition_health = DEGRADED
no más restart thrashing
metric behavior permanece conservador
```

---

# 8. Health model

Separar:

## 8.1 Global scanner health

```text
GLOBAL_SCANNER_HEALTHY
GLOBAL_SCANNER_STALLED
GLOBAL_SCANNER_ERROR
```

Basado en:

```text
last_any_scan_result_age_ms
scan failure callback
Bluetooth state
```

## 8.2 Body Finder cohort health

```text
BF_COHORT_HEALTHY
BF_COHORT_SPARSE
BF_COHORT_STALLED
BF_COHORT_RECOVERING
BF_COHORT_UNAVAILABLE
```

Basado en:

```text
known active fabric peers
last valid Body Finder callback per peer
last any Body Finder callback
number of peers recently observed
```

---

# 9. Stall detection

Propuesta inicial:

```text
active_fabric_peer_count >= 1

AND
global scanner healthy

AND
last_any_scan_result_age_ms <= 2000

AND
last_body_finder_scan_result_age_ms > 5000

AND
recent_body_finder_peer_count == 0
```

entonces:

```text
BF_COHORT_STALLED
```

Esta condición detecta exactamente el patrón visto en `dev-8`.

## 9.1 Single-peer gap

Si solo un peer desaparece:

```text
BF_COHORT_SPARSE
```

pero no reiniciar globalmente inmediatamente.

## 9.2 Full-cohort stall

Si todos los peers Body Finder desaparecen simultáneamente:

```text
eligible for controlled recovery
```

---

# 10. Recovery sequence

```text
FILTERED_PRIMARY
       │
       │ BF_COHORT_STALLED > stall threshold
       ▼
STOP scanner
       │
       ▼
short quiet interval
       │
       ▼
START UNFILTERED_RECOVERY
       │
       │ Body Finder peer callbacks recovered
       ▼
collect recovery window
       │
       ▼
FILTERED_RECOVERY_PROBE
       │
       ├─ peers stable → FILTERED_PRIMARY
       │
       └─ stall again → bounded retry / cooldown
```

---

# 11. Recovery timing

Propuesta inicial versionada:

```text
COHORT_STALL_THRESHOLD_MS = 5000
RECOVERY_UNFILTERED_WINDOW_MS = 10000
FILTERED_PROBE_WINDOW_MS = 15000
MIN_RESTART_COOLDOWN_MS = 30000
MAX_RECOVERY_ATTEMPTS_PER_5_MIN = 3
```

Estos valores deben ser cubiertos por tests y visibles en diagnostics.

No ocultar thresholds dentro de magic numbers.

---

# 12. Anti-thrashing

Nunca repetir:

```text
stop
start
stop
start
...
```

sin límite.

Registrar:

```text
scan_restart_total
scan_restart_run_delta
strategy_transition_total
strategy_transition_run_delta
cohort_recovery_attempt_count
cohort_recovery_suppressed_count
```

Si excede:

```text
MAX_RECOVERY_ATTEMPTS_PER_5_MIN
```

pasar a:

```text
FAILED_SAFE
```

hasta terminar cooldown.

---

# 13. Recovery success criteria

Un recovery se considera exitoso si:

```text
Body Finder peer callback received
+
payload valid
+
known/current session peer
```

Registrar:

```text
recovery_started_ms
recovery_first_bf_callback_ms
cohort_recovery_latency_ms
```

---

# 14. Strategy provenance

Por runtime/export:

```json
{
  "acquisition_strategy": "FILTERED_PRIMARY",
  "strategy_since_ms": 12345,
  "strategy_transition_count": 3,
  "cohort_health": "BF_COHORT_HEALTHY",
  "cohort_stall_count": 1,
  "cohort_recovery_count": 1,
  "cohort_recovery_last_latency_ms": 721
}
```

---

# 15. Per-peer acquisition diagnostics

Mantener de dev-8:

```text
callback_count
valid_rssi_callback_count
invalid_rssi_callback_count

callback_rate_hz
valid_callback_rate_hz

mean_interarrival_ms
p50_interarrival_ms
p95_interarrival_ms
max_interarrival_ms

gap_gt_1s
gap_gt_2s
gap_gt_5s
gap_gt_10s
```

Añadir:

```text
last_callback_strategy
last_valid_callback_strategy
callbacks_filtered_mode
callbacks_unfiltered_mode

run_callbacks_filtered_delta
run_callbacks_unfiltered_delta

peer_stall_count
peer_recovery_count
peer_recovery_latency_ms
```

---

# 16. Cohort-level diagnostics

Añadir:

```text
recent_known_peer_count
expected_known_peer_count

last_bf_cohort_callback_age_ms

cohort_stall_count
cohort_recovery_count
cohort_recovery_failure_count

filtered_mode_total_ms
unfiltered_recovery_total_ms

strategy_transition_count
restart_suppressed_by_cooldown_count
```

---

# 17. Battery Saver validation gate

Antes de iniciar una validation run:

```text
power_save_mode == true
```

debe:

```text
BLOCK validation run
```

y mostrar:

```text
VALIDATION_ENVIRONMENT_INVALID
Battery Saver must be OFF
```

No basta con registrar el problema después.

También validar:

```text
screen_state = ON
app_visibility = active
foreground_service_state = RUNNING
Bluetooth = ON
```

Si alguno falla al inicio:

```text
run cannot start
```

---

# 18. Runtime environmental drift

Si Battery Saver se activa durante una corrida:

```text
validation_environment_degraded = true
```

Registrar:

```text
environment_violation_count
first_environment_violation_ms
environment_violation_types
```

No invalidar automáticamente datos anteriores, pero marcar toda la corrida como:

```text
TEST_ENVIRONMENT_INVALID
```

para acceptance.

---

# 19. RangingManager coexistence

Mantener exactamente el comportamiento de `dev-8`:

```text
session open != success
real distance resets failure
repeated close/no-result → BLE_ACQUISITION_YIELD
yield = 120 s
```

No tocar salvo instrumentación adicional.

Añadir únicamente correlación:

```text
ranging_yield_active_at_cohort_stall
ranging_yield_transition_count
```

para análisis causal.

---

# 20. Metric/geometry rules

No cambiar.

`experimental.9` solo debe mejorar adquisición.

```text
FRESH
HOLDOVER
EXPIRED
```

se conservan sin modificación.

Si recovery tarda demasiado y el holdover vence:

```text
edge expires
```

aunque eso reduzca temporalmente 2D.

Truthfulness sigue teniendo prioridad.

---

# 21. Backlog atómico

## EPIC A — Baseline freeze

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| A-001 | P0 | TL | Congelar calibration profile | — | CI guard |
| A-002 | P0 | TL | Congelar minSamples=3 | — | CI guard |
| A-003 | P0 | TL | Congelar fresh=5s | — | CI guard |
| A-004 | P0 | TL | Congelar holdover=10s | — | CI guard |
| A-005 | P0 | TL | Congelar sigma aging | — | CI guard |
| A-006 | P0 | QAE | Fixture dev-8 physical failure | — | Reproducible |

## EPIC B — Restore filtered primary

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| B-001 | P0 | ABP | Crear filtered ScanFilter Body Finder | A | Unit/static |
| B-002 | P0 | ABP | FILTERED_PRIMARY low latency | B-001 | Runtime |
| B-003 | P0 | ABP | reportDelay=0 | B-001 | Runtime |
| B-004 | P0 | ABP | API23 aggressive matching | B-001 | Runtime |
| B-005 | P0 | QAE | Primary hardware filter count >0 | B-* | PASS |

## EPIC C — Preserve unfiltered fallback

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| C-001 | P0 | ABP | Definir UNFILTERED_RECOVERY config | B | Runtime |
| C-002 | P0 | ABP | Mantener software payload validation | C-001 | Correct |
| C-003 | P0 | QAE | Unfiltered no primary by default | C-* | PASS |

## EPIC D — Global scanner health

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| D-001 | P0 | PSM | Definir GLOBAL_SCANNER_HEALTHY | — | Enum |
| D-002 | P0 | PSM | Definir GLOBAL_SCANNER_STALLED | — | Enum |
| D-003 | P0 | ABP | Implement global health calculation | D-* | Tests |
| D-004 | P0 | QAE | generic callback fresh => global healthy | D-* | PASS |

## EPIC E — Body Finder cohort health

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| E-001 | P0 | PSM | Definir BF_COHORT_HEALTHY | — | Enum |
| E-002 | P0 | PSM | Definir BF_COHORT_SPARSE | — | Enum |
| E-003 | P0 | PSM | Definir BF_COHORT_STALLED | — | Enum |
| E-004 | P0 | PSM | Definir BF_COHORT_RECOVERING | — | Enum |
| E-005 | P0 | ABP | Track last BF cohort callback | E-* | Export |
| E-006 | P0 | ABP | Track recent known peers | E-* | Export |
| E-007 | P0 | QAE | Global healthy + BF stale => cohort stalled | E-* | PASS |

## EPIC F — Stall detector

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| F-001 | P0 | RAR | Define 5s cohort stall threshold | E | Versioned |
| F-002 | P0 | RAR | Define global fresh <=2s | E | Versioned |
| F-003 | P0 | PSM | Implement full-cohort rule | F-* | Tests |
| F-004 | P0 | PSM | Implement single-peer sparse rule | F-* | Tests |
| F-005 | P0 | QAE | dev-8 timeline detects stall | F-* | PASS |

## EPIC G — Acquisition state machine

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| G-001 | P0 | PSM | Enum FILTERED_PRIMARY | B | Compile |
| G-002 | P0 | PSM | Enum UNFILTERED_RECOVERY | C | Compile |
| G-003 | P0 | PSM | Enum FILTERED_RECOVERY_PROBE | — | Compile |
| G-004 | P0 | PSM | Enum COOLDOWN | — | Compile |
| G-005 | P0 | PSM | Enum FAILED_SAFE | — | Compile |
| G-006 | P0 | PSM | Implement transition table | G-* | Tests |

## EPIC H — Controlled scanner restart

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| H-001 | P0 | ABP | Stop scanner cleanly | G | No leak |
| H-002 | P0 | ABP | Quiet interval before restart | H-001 | Deterministic |
| H-003 | P0 | ABP | Start recovery mode | H-* | Runtime |
| H-004 | P0 | ABP | Preserve node identity state | H-* | Test |
| H-005 | P0 | QAE | Restart does not expire fabric peers | H-* | PASS |

## EPIC I — Recovery timing

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| I-001 | P0 | RAR | Set unfiltered recovery window=10s | G | Constant |
| I-002 | P0 | RAR | Set filtered probe=15s | G | Constant |
| I-003 | P0 | RAR | Set restart cooldown=30s | G | Constant |
| I-004 | P0 | RAR | Set max attempts/5m=3 | G | Constant |
| I-005 | P0 | QAE | Boundary tests | I-* | PASS |

## EPIC J — Anti-thrashing

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| J-001 | P0 | PSM | Count recovery attempts | I | Export |
| J-002 | P0 | PSM | Suppress restart during cooldown | I | Test |
| J-003 | P0 | PSM | FAILED_SAFE after max attempts | I | Test |
| J-004 | P0 | QAE | Simulate repeated stalls | J-* | no thrash |

## EPIC K — Recovery success

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| K-001 | P0 | ABP | Detect first valid BF callback after recovery | H | Timestamp |
| K-002 | P0 | RAR | Compute recovery latency | K-001 | Export |
| K-003 | P0 | PSM | Transition to filtered probe | K-* | Test |
| K-004 | P0 | PSM | Return to filtered primary after stable probe | K-* | Test |
| K-005 | P0 | QAE | Recovery success timeline | K-* | PASS |

## EPIC L — Strategy telemetry

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| L-001 | P0 | PSM | Export strategy | G | JSON |
| L-002 | P0 | PSM | Export strategy_since_ms | G | JSON |
| L-003 | P0 | PSM | Export strategy_transition_count | G | JSON |
| L-004 | P0 | RAR | Export filtered total time | G | JSON |
| L-005 | P0 | RAR | Export unfiltered total time | G | JSON |
| L-006 | P0 | QAE | Schema tests | L-* | PASS |

## EPIC M — Per-peer mode provenance

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| M-001 | P1 | ABP | last_callback_strategy | L | Export |
| M-002 | P1 | ABP | callbacks_filtered_mode | L | Export |
| M-003 | P1 | ABP | callbacks_unfiltered_mode | L | Export |
| M-004 | P1 | QAE | Per-peer counts reconcile total | M-* | PASS |

## EPIC N — Cohort diagnostics

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| N-001 | P0 | MUD | Show global scanner health | D | UI |
| N-002 | P0 | MUD | Show BF cohort health | E | UI |
| N-003 | P0 | MUD | Show last BF cohort age | E | UI |
| N-004 | P0 | MUD | Show recovery count | K | UI |
| N-005 | P0 | MUD | Show last recovery latency | K | UI |
| N-006 | P0 | QAE | UI snapshot tests | N-* | PASS |

## EPIC O — Battery Saver validation gate

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| O-001 | P0 | MUD | Detect power_save_mode before run | — | UI |
| O-002 | P0 | MUD | Block run if ON | O-001 | Test |
| O-003 | P0 | MUD | Show corrective message | O-001 | UX |
| O-004 | P0 | PSM | Export environment validity | O-* | JSON |
| O-005 | P0 | QAE | Battery Saver ON test | O-* | PASS |

## EPIC P — Environment drift

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| P-001 | P1 | ABP | Detect power saver during active run | O | Event |
| P-002 | P1 | PSM | environment_violation_count | P-001 | Export |
| P-003 | P1 | PSM | first violation time | P-001 | Export |
| P-004 | P1 | MUD | Mark TEST_ENVIRONMENT_INVALID | P-* | UI/export |
| P-005 | P1 | QAE | Drift test | P-* | PASS |

## EPIC Q — RangingManager regression

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| Q-001 | P0 | QAE | Real result resets failures | — | PASS |
| Q-002 | P0 | QAE | session open does not reset | — | PASS |
| Q-003 | P0 | QAE | yield remains 120s | — | PASS |
| Q-004 | P1 | PSM | Correlate yield with cohort stall | E | Export |

## EPIC R — Metric truth regression

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| R-001 | P0 | QAE | Profile unchanged | A | PASS |
| R-002 | P0 | QAE | domain unchanged | A | PASS |
| R-003 | P0 | QAE | minSamples unchanged | A | PASS |
| R-004 | P0 | QAE | holdover unchanged | A | PASS |
| R-005 | P0 | QAE | RSSI127 still filtered | — | PASS |
| R-006 | P0 | QAE | no silent clamp | — | PASS |
| R-007 | P0 | QAE | reciprocal REJECT excluded | — | PASS |

## EPIC S — Geometry regression

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| S-001 | P0 | QAE | dev-6 accuracy fixture | R | PASS |
| S-002 | P0 | QAE | dev-7 holdover fixture | R | PASS |
| S-003 | P0 | QAE | dev-8 stall fixture | F | Detect |
| S-004 | P0 | QAE | 3 fresh edges -> 2D | — | PASS |
| S-005 | P0 | QAE | expired edge excluded | — | PASS |

## EPIC T — Validation run metrics

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| T-001 | P0 | PSM | acquisition_strategy_transition_delta | L | JSON |
| T-002 | P0 | PSM | cohort_stall_delta | N | JSON |
| T-003 | P0 | PSM | cohort_recovery_delta | N | JSON |
| T-004 | P0 | PSM | recovery_failure_delta | N | JSON |
| T-005 | P0 | PSM | recovery latency stats | K | JSON |
| T-006 | P0 | QAE | Run-scoped counter tests | T-* | PASS |

## EPIC U — Expert/Radar

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| U-001 | P0 | MUD | Badge FILTERED_PRIMARY | L | Visible |
| U-002 | P0 | MUD | Badge UNFILTERED_RECOVERY | L | Visible |
| U-003 | P0 | MUD | BF_COHORT_STALLED warning | N | Visible |
| U-004 | P1 | MUD | Recovery latency summary | K | Visible |
| U-005 | P0 | QAE | Truthful UI states | U-* | PASS |

## EPIC V — CI

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| V-001 | P0 | DRE | Add acquisition strategy contract | all | CI |
| V-002 | P0 | DRE | Guard filtered primary | B | CI |
| V-003 | P0 | DRE | Guard ALL_MATCHES recovery-only | C | CI |
| V-004 | P0 | DRE | Guard cohort stall detector | F | CI |
| V-005 | P0 | DRE | Guard max attempts/cooldown | J | CI |
| V-006 | P0 | DRE | Battery Saver gate tests | O | CI |
| V-007 | P0 | DRE | Android universal build | all | Green |
| V-008 | P0 | DRE | Android legacy build | all | Green |
| V-009 | P1 | DRE | Linux regression | all | Green |
| V-010 | P1 | DRE | Windows regression | all | Green |
| V-011 | P1 | DRE | iOS simulator regression | all | Green |

## EPIC W — Release

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| W-001 | P0 | DRE | Bump experimental.9 | — | Version |
| W-002 | P0 | DRE | versionCode bump | — | Android |
| W-003 | P0 | DRE | report_version bump | — | Schema |
| W-004 | P0 | DRE | release manifest strategy fields | all | Present |
| W-005 | P0 | DRE | adaptive acquisition fixtures zip | all | Artifact |
| W-006 | P0 | DRE | SBOM | all | Artifact |
| W-007 | P0 | DRE | SHA256SUMS | all | Verify |
| W-008 | P0 | TL | Confirm human scanning false | W-* | Truth |

## EPIC X — Physical retest

| ID | Pri | Owner | Tarea | Dependencia | Aceptación |
|---|---|---|---|---|---|
| X-001 | P0 | FVE | Same 3 Androids | Release | Homogeneous |
| X-002 | P0 | FVE | Battery Saver OFF verified | O | Valid env |
| X-003 | P0 | FVE | Screens ON / foreground | — | Valid env |
| X-004 | P0 | FVE | Same triangle 0.5–5m | — | Layout |
| X-005 | P0 | FVE | 5 min validation run | — | Complete |
| X-006 | P0 | FVE | End run before export | — | active=false |
| X-007 | P0 | FVE | Export 3 JSON | — | Evidence |
| X-008 | P0 | FVE | Capture adaptive strategy screenshots | — | Evidence |
| X-009 | P0 | RAR | Analyze six directional links | X-* | Report |
| X-010 | P0 | RAR | Analyze cohort recovery | X-* | Report |
| X-011 | P0 | RAR | Analyze usable metric uptime | X-* | >=90% |
| X-012 | P0 | RAR | Analyze Geometry2D uptime | X-* | >=90% |
| X-013 | P0 | TL | Decide human-test authorization | X-* | Explicit |

---

# 22. Acceptance gates

## G0 — Physical invariants

```text
profile unchanged
RSSI@1m unchanged
n unchanged
domain unchanged
minSamples=3
holdover=10s
```

## G1 — Filtered primary

At startup:

```text
acquisition_strategy = FILTERED_PRIMARY
hardware_filter_count > 0
```

## G2 — Cohort stall detection

When:

```text
generic BLE continues
Body Finder cohort disappears >5s
```

must become:

```text
BF_COHORT_STALLED
```

## G3 — Recovery

A full-cohort stall triggers at most one controlled recovery subject to cooldown.

## G4 — Anti-thrashing

In a 5-minute run:

```text
recovery attempts <= 3
```

unless explicitly justified by a test fixture.

## G5 — Environment validity

Run cannot begin with Battery Saver ON.

## G6 — Uptime

On all 3 devices:

```text
usable_metric_range_uptime_percent >= 90%
geometry_2d_uptime_percent >= 90%
peer_expire_delta = 0
```

Preferred:

```text
all_peer_uptime_percent >= 99%
scan_restart_delta <= 3
```

## G7 — Recovery health

No unexplained full-cohort stall >10 s should remain unrecovered unless state transitions to FAILED_SAFE and is reported truthfully.

---

# 23. Physical retest protocol for experimental.9

Use:

```text
Pixel 10 Pro
Pixel 7 Pro
Lenovo TB-J606L
```

Conditions:

```text
same APK experimental.9
same LAN
Bluetooth ON
Battery Saver OFF
screen ON
foreground
Lenovo Location ON
```

Layout:

```text
non-collinear triangle
all pair distances 0.5–5 m
```

Procedure:

```text
open all apps
wait 30 s
verify 3 nodes / 2 BLE peers
verify FILTERED_PRIMARY
start validation run on all 3
leave stationary 5 min
end run
wait 2 s
capture screenshots
export full JSON
```

---

# 24. Evidence required

Files:

```text
pixel10_adaptive_acquisition.txt
pixel7_adaptive_acquisition.txt
lenovo_adaptive_acquisition.txt
```

Screenshots:

```text
pixel10_radar.png
pixel10_validation.png
pixel10_ble.png
pixel10_acquisition_strategy.png
pixel10_system_ranging.png

pixel7_radar.png
pixel7_validation.png
pixel7_ble.png
pixel7_acquisition_strategy.png

lenovo_radar.png
lenovo_validation.png
lenovo_ble.png
lenovo_acquisition_strategy.png
```

Important fields:

```text
global_scanner_health
body_finder_cohort_health

acquisition_strategy
strategy_transition_count

cohort_stall_count
cohort_recovery_count
cohort_recovery_failure_count
cohort_recovery_latency_ms

filtered_mode_total_ms
unfiltered_recovery_total_ms

restart_suppressed_by_cooldown_count

per-peer:
callback_rate_hz
valid_callback_rate_hz
p95_interarrival_ms
gap_gt_1s
gap_gt_2s
gap_gt_5s
gap_gt_10s
```

Validation run:

```text
environment_valid

all_peer_uptime_percent
fresh_metric_range_uptime_percent
usable_metric_range_uptime_percent
holdover_metric_uptime_percent
geometry_2d_uptime_percent

peer_expire_delta
scan_restart_delta
strategy_transition_delta
cohort_stall_delta
cohort_recovery_delta
```

---

# 25. Release artifacts expected

```text
body-finder-ruview-universal.apk
body-finder-ruview.aab
body-finder-ruview-legacy-minsdk21.apk

body-finder-node-linux-x86_64.tar.gz
body-finder-node-linux-x86_64.deb
body-finder-node-windows-x86_64.zip
body-finder-ruview-ios-simulator.zip

IMPLEMENTATION_PLAN_BLE_ADAPTIVE_ACQUISITION_RECOVERY.md
ANDROID_BLE_ADAPTIVE_ACQUISITION_RETEST.md

ble-adaptive-acquisition-regression-fixtures.zip
ble-acquisition-regression-fixtures.zip
ble-continuity-regression-fixtures.zip
ble-range-calibration-fixtures.zip
body-finder-validation-tools.zip

ble-range-calibration-profiles.json
ble-range-calibration-schema.json

release-manifest.json
capability-matrix.json
protocol-version.txt
ruview-upstream-lock.json
model-manifest.json
SHA256SUMS
SBOM.spdx.json
```

---

# 26. Expected release manifest fields

```json
{
  "version": "0.2.0-experimental.9",
  "protocol_version": 2,

  "ble_metric_profile": "android-ble-lab-v1",
  "ble_metric_profile_validated": true,

  "ble_primary_strategy": "FILTERED_PRIMARY",
  "ble_recovery_strategy": "UNFILTERED_RECOVERY",

  "ble_body_finder_cohort_health": true,
  "ble_global_scanner_health_separate": true,

  "ble_cohort_stall_threshold_ms": 5000,
  "ble_global_scanner_fresh_ms": 2000,

  "ble_recovery_unfiltered_window_ms": 10000,
  "ble_filtered_probe_window_ms": 15000,
  "ble_restart_cooldown_ms": 30000,
  "ble_max_recovery_attempts_per_5min": 3,

  "validation_blocks_battery_saver": true,

  "human_scanning_enabled": false,
  "human_localization_validated": false,
  "rescue_use_validated": false
}
```

---

# 27. Risks

| Riesgo | Prob | Impacto | Mitigación |
|---|---:|---:|---|
| Filtered mode vuelve a degradarse | Media | Alto | adaptive fallback |
| Recovery causes thrashing | Media | Alto | cooldown + max attempts |
| ALL_MATCHES still unstable | Alta | Medio | recovery-only, bounded |
| false cohort stall | Media | Medio | require active known peers + global healthy |
| one-peer loss triggers global restart | Media | Alto | SPARSE != STALLED |
| Battery Saver contaminates run | Media | Alto | block start |
| recovery hides real stale data | Baja | Alto | holdover unchanged |
| Pixel vendor behavior varies | Alta | Medio | strategy provenance + per-device telemetry |

---

# 28. Definition of Done global

El incremento está terminado únicamente cuando:

1. filtered scanning vuelve a ser primary;
2. ALL_MATCHES queda recovery-only;
3. global scanner health y BF cohort health están separados;
4. dev-8 stall fixture dispara BF_COHORT_STALLED;
5. recovery controlado funciona;
6. cooldown impide thrashing;
7. max recovery attempts se respeta;
8. recovery latency se mide;
9. strategy transitions se exportan;
10. Battery Saver bloquea validation run;
11. environment drift se reporta;
12. RangingManager yield permanece funcional;
13. profile/calibration no cambian;
14. minSamples/holdover no cambian;
15. reciprocal fusion no cambia;
16. solver no cambia;
17. CI completo verde;
18. experimental.9 publicado;
19. physical retest de 5 minutos ejecutado;
20. usable metric >=90% en los 3;
21. Geometry2D >=90% en los 3;
22. human scanning sigue bloqueado hasta decisión explícita.

---

# 29. Checklist final del Tech Lead

- [ ] Profile congelado.
- [ ] minSamples=3.
- [ ] fresh=5s.
- [ ] holdover=10s.
- [ ] sigma aging sin cambios.
- [ ] FILTERED_PRIMARY activo al inicio.
- [ ] UNFILTERED_RECOVERY no es primary.
- [ ] Global scanner health separado.
- [ ] BF cohort health separado.
- [ ] BF_COHORT_STALLED implementado.
- [ ] BF_COHORT_SPARSE implementado.
- [ ] Controlled restart.
- [ ] Recovery window bounded.
- [ ] Filtered recovery probe.
- [ ] Cooldown.
- [ ] Max attempts.
- [ ] FAILED_SAFE.
- [ ] Recovery latency.
- [ ] Strategy provenance.
- [ ] Per-peer strategy provenance.
- [ ] Battery Saver gate.
- [ ] Environment invalidation.
- [ ] RangingManager yield preserved.
- [ ] dev-6 precision regression green.
- [ ] dev-7 continuity regression green.
- [ ] dev-8 stall fixture green.
- [ ] Android universal build green.
- [ ] Android legacy build green.
- [ ] Linux/Windows/iOS regressions green.
- [ ] experimental.9 release.
- [ ] 5-min adaptive acquisition retest.
- [ ] usable metric >=90% all 3.
- [ ] Geometry2D >=90% all 3.
- [ ] human scanning authorization explicitly reviewed.
- [ ] rescue_use_validated=false.

---

**Fin del plan.**
