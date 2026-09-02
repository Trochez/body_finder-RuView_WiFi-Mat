# dev-20.15 — prueba física G10

1. Desinstale Body Finder en Pixel 10 Pro, Pixel 7 Pro y Lenovo; instale el APK universal `dev-20.15`.
2. Forme un triángulo no colineal (baselines BLE 0.5–5.0 m), misma LAN, Bluetooth/screen/app foreground ON, battery saver OFF. Abra los nodos separados ~10 s.
3. No continúe hasta ver en los tres: Authority 3/3, mismo coordinator/generation/digest, 3 posiciones `GEOMETRY_2D`. Calibre **solo en el coordinator**. Exija mismo calibration id/hash/generation, Calibration ACK 3/3 y 0 required-control oversize. Si falla, exporte exactamente 3 PRE_RUN JSON y termine.
4. `SMOKE_CAL_EMPTY`: Scenario ACK 3/3 -> RunStart READY 3/3+COMMIT -> >=330 s -> Freeze/Snapshot READY 3/3+COMMIT. Exporte 1 JSON por nodo (3).
5. Sin mover ni recalibrar nodos: `HUMAN_MOVING`, persona moviéndose >=330 s, mismos barriers, freeze y exporte 1 JSON por nodo (3).
6. Ejecute: `python3 validation/analysis/validate_dev20_15_g10.py <los 6 JSON>`. Solo `GO` habilita G11/dev21. Screenshots no requeridos.
