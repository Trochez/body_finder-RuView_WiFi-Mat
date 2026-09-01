# TESTING dev-20.12

1. Instala `BodyFinder-dev20.12-universal.apk` limpio en Pixel 10 Pro, Pixel 7 Pro y Lenovo TB-J606L. Misma LAN; Bluetooth/permisos listos; Battery Saver OFF; pantallas ON; app foreground; Location ON en Lenovo si se requiere. No ingreses coordenadas manuales.
2. Forma un triángulo fijo no colineal (cada par 0.5–5.0 m). Espera exactamente 2 peers/dispositivo, coordinador estable, range usable y Geometry2D. Calibra EMPTY **solo en el coordinador** y no continúes hasta `Calibration ACK 3/3` con mismo ID/hash/generation/topology hash.
3. Coordinador: emite `SMOKE_CAL_EMPTY`, exige Scenario ACK 3/3 y pulsa Start **una sola vez**. Espera RunStart READY/COMMIT 3/3; los peers arrancan automáticamente con el mismo `campaign_run_token`. Mantén EMPTY >=330 s.
4. Coordinador: pulsa End **una sola vez**. Espera SnapshotReady 3/3 y RunFreezeCommitV2; los peers terminan automáticamente. Exporta exactamente un JSON/dispositivo solo cuando el snapshot distribuido esté committed 3/3.
5. Sin mover nodos ni recalibrar, repite 3–4 con `HUMAN_MOVING`, una persona moviéndose >=330 s. Obtén otros 3 JSON. No uses screenshots.
6. Extrae `validators-dev20.12.zip` y ejecuta: `python3 validation/analysis/validate_dev20_12_smoke.py --evidence-dir <carpeta_6_json> --detector ./body-finder-detector-linux-x86_64 --output g10-dev20.12.json` (Windows: detector `.exe`).
7. Solo continúa a G11 si `g10_go=true`. Si falla cualquier gate, DETENTE y comparte únicamente los 6 JSON + `g10-dev20.12.json`; no ejecutes G11.

Hard gates: 3 EMPTY + 3 HUMAN; cada run >=330000 ms; environment valid; peer expiry 0; range usable >=90%; Geometry2D >=90%; critical control failures 0; required oversize 0; CONTROL <=900 B; datagram <=1200 B; Scenario/Calibration/RunStart/SnapshotReady/RunFreeze 3/3; misma authority identity; artifacts calibration/final-decision completos; 3 nodes/6 links/3 baselines; replay/digest parity; evidence + atomic validity exact; EMPTY=NO_HUMAN_EVIDENCE y HUMAN_MOVING=HUMAN_EVIDENCE.
