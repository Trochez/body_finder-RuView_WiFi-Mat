# TESTING dev-20.17 — G10

No screenshots. Los JSON exportados son la evidencia autoritativa.

## Preparación

1. Descarga `BodyFinder-dev20.17-universal.apk`, `validate_dev20_17_prerun.py` y `validate_dev20_17_g10.py` del release `dev-20.17` y verifica `SHA256SUMS.txt`.
2. Clean-install **el mismo APK** en exactamente 3 Android. Activa Bluetooth/permisos, app foreground y desactiva battery saver.
3. No muevas los nodos después de calibrar.

## PRE_RUN

4. Espera en los 3 nodos: **2 peers**, `Authority ACK 3/3` y `GEOMETRY_2D`.
5. En el coordinator únicamente, calibra EMPTY y espera `Calibration ACK 3/3` + `calibration_ack_symmetric=true`.
6. En coordinator selecciona `SMOKE_CAL_EMPTY`; espera `Scenario ACK 3/3`.
7. Pulsa **Start una sola vez** en coordinator. No inicies cronómetro hasta ver `RunStart READY 3/3` y `COMMIT=true`.
8. Si no converge: exporta **exactamente 3 PRE_RUN JSON**, uno por nodo, detén la campaña y ejecuta:

```bash
python3 validate_dev20_17_prerun.py pre-run-*.json --output prerun-result.json
```

## G10

9. Si PRE_RUN converge, ejecuta `SMOKE_CAL_EMPTY` durante **>=330 s**.
10. End solo en coordinator; espera `Freeze READY 3/3` y `COMMIT=true`; después exporta 3 JSON acceptance.
11. Sin recalibrar ni mover nodos, selecciona `HUMAN_MOVING`, Start una vez, espera RunStart 3/3+COMMIT y ejecuta **>=330 s**.
12. End solo en coordinator; espera Freeze 3/3+COMMIT; exporta otros 3 JSON.
13. Debes tener exactamente 6 JSON: 3 `SMOKE_CAL_EMPTY` + 3 `HUMAN_MOVING`, de 3 node IDs únicos. Ejecuta:

```bash
python3 validate_dev20_17_g10.py *.json --output g10-result-dev20.17.json
```

## Criterio

`GO` requiere: Authority/Scenario/Calibration 3/3, Calibration simétrica, mismo `campaign_run_token`, RunStart 3/3+COMMIT, Freeze 3/3+COMMIT, `critical_control_failure_count=0`, cero oversize y cada corrida >=330000 ms. Ante cualquier NO-GO, comparte solamente los JSON + resultado del validator; no screenshots.
