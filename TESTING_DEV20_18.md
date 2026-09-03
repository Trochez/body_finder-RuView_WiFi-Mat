# TESTING DEV-20.18

1. Clean-install `BodyFinder-dev20.18-universal.apk` on exactly 3 Androids.
2. Wait for peers **2/2**, Authority **3/3** and `GEOMETRY_2D`.
3. Calibrate EMPTY **once on coordinator only**.
4. Continue only when all 3 show the same **current** calibration ID/hash/generation/topology, local artifact promoted, Calibration ACK **3/3** and `distributed_calibration_ready=true`.
5. Issue `SMOKE_CAL_EMPTY`; require Scenario **3/3**.
6. Press Start once on coordinator; require a **fresh** RunStart **3/3 + COMMIT** bound to the current calibration.
7. If any pre-run gate fails, export exactly **3 PRE_RUN JSONs** and STOP.
8. Otherwise run EMPTY >=330 s; End on coordinator; require Freeze **3/3**; export 3 JSONs.
9. Without moving/recalibrating, run `HUMAN_MOVING` >=330 s; Freeze **3/3**; export 3 JSONs.
10. Run `python validate_dev20_18_g10.py <exactly six JSONs>`. Share JSON + verdict only; screenshots are unnecessary.
