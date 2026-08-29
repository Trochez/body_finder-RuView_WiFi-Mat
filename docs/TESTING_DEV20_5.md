# TESTING DEV-20.5

## Smoke obligatorio (6 JSON)
1. Instala `BodyFinder-dev20.5-universal.apk` en Pixel 10 Pro, Pixel 7 Pro y Lenovo TB-J606L. Confirma build `0.2.0-experimental.20.5`; Wi-Fi/Bluetooth ON, Battery Saver OFF, pantallas ON/app foreground; Location ON en Lenovo si Android lo exige.
2. Limpia sesión previa. Ubica los 3 equipos en triángulo fijo no colineal y espera exactamente 2 peers por nodo.
3. Solo en el coordinador inicia calibración EMPTY. Continúa únicamente cuando los tres JSON reporten el mismo calibration id/hash/generation y `distributed_calibration_ready=true`.
4. Selecciona **EMPTY**. Ejecuta 60–90 s sin persona ni mover nodos; exporta 1 JSON/dispositivo.
5. Sin recalibrar ni mover nodos selecciona **HUMAN MOVING**. Ejecuta 60–90 s con una persona moviéndose dentro del triángulo; exporta 1 JSON/dispositivo.
6. Ejecuta: `python3 validate_dev20_5_smoke.py --detector ./body-finder-detector-linux-x86_64 --output smoke-go-no-go.json <6-json>`.
7. GO solo con exit=0 y `final_go=true`. Si falla, detente y comparte los 6 JSON. No se requieren screenshots.

## Campaña final (solo después de smoke GO)
Congela commit/APK/detector/schema/parámetros. Dos días independientes × 9 escenarios × 3 dispositivos = 54 JSON frescos, >=330 s por escenario:
`EMPTY_CAL`, `EMPTY_TEST`, `HUMAN_STATIONARY_CENTER`, `HUMAN_MOVING`, `HUMAN_NEAR_LENOVO`, `HUMAN_NEAR_PIXEL10`, `HUMAN_NEAR_PIXEL7`, `HUMAN_OUTSIDE`, `NON_HUMAN_MOTION`.

Ejecuta `python3 build_dev20_5_campaign.py --output dev20.5-campaign-report.json <54-json>`.
Acepta solo recall>=0.90, specificity>=0.85, indeterminate<=0.10, stationary recall>=0.80, moving recall>=0.90 y paridad peer/Android↔CLI exacta. Cualquier cambio posterior invalida TEST y exige recollectar. `human_localization_validated=false`, `rescue_use_validated=false`.
