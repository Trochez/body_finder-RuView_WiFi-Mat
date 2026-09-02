# dev-20.16 — prueba física G10

## Objetivo
Validar la remediación de convergencia distribuida de calibración y recuperación BLE usando exclusivamente los JSON exportados por la app. No se requieren screenshots.

## Dispositivos
Use exactamente 3 Android físicos con Bluetooth habilitado, permisos concedidos, ahorro de batería desactivado, app en foreground y el mismo `session_id`/cohort.

## Instalación
1. Descargue `BodyFinder-dev20.16-universal.apk` desde la release `dev-20.16` e instálelo en los 3 Android.
2. Verifique en la app build `0.2.0-experimental.20.16`.
3. Mantenga los tres nodos activos hasta obtener autoridad 3/3, geometría `GEOMETRY_2D` y calibración distribuida 3/3.

## Campaña requerida
Ejecute 6 corridas, cada una de al menos 330 s:

- 3 corridas `SMOKE_CAL_EMPTY` (una exportación JSON por nodo/corrida según el flujo de validación de la app).
- 3 corridas `HUMAN_MOVING`.

Para la aceptación final entregue exactamente 6 JSON representativos que cubran 3 nodos únicos y ambos escenarios 3+3, tal como exige el validator incluido en la release.

## Condiciones que deben mantenerse
- authority ACK = 3/3.
- `GEOMETRY_2D`.
- calibration ACK = 3/3 y `calibration_ack_symmetric=true`.
- mismo `calibration_id`, `calibration_hash`, `calibration_generation`, `topology_hash`, coordinator y authority digest entre nodos.
- `topology_hash = SHA256(topology_fingerprint)` exactamente una vez; double-hash es NO-GO.
- acquisition fuera de `FAILED_SAFE`, `UNFILTERED_RECOVERY`, `FILTERED_RECOVERY_PROBE` o recovery agotado al cierre.
- `scenario_ack_count=3`, `runstart_ready_count=3` + commit y `freeze_ready_count=3` + commit.
- `critical_control_failure_count=0` y oversize=0.
- observación primaria fresca y foreground válido.

## Validación
Con Python 3:

```bash
python validate_dev20_16_g10.py run1.json run2.json run3.json run4.json run5.json run6.json --output g10-result.json
```

Resultado esperado:

```text
g10 = GO
g10_go = true
g11 = UNBLOCKED
dev21 = UNBLOCKED
```

Si el validator devuelve NO_GO, comparta los 6 JSON originales y `g10-result.json`; contienen la evidencia suficiente para diagnóstico sin screenshots.

## Integridad de release
Antes de probar, opcionalmente verifique todos los assets descargados con `SHA256SUMS.txt`. `release-verification.json` debe indicar `release_integrity=true` y `release_redownload_sha_verified=true`.
