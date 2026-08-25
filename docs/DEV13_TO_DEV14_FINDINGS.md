# dev13 → dev14 closure matrix

| dev13 finding | dev14 fix | automated gate |
|---|---|---|
| RECOVERY_START_MISSING | terminal event and probe transition are atomic; recovery provenance survives probe | timeline + Android contract |
| FILTERED_PROBE_WINDOW_EXPIRED | 14.5 s internal exit target, 15 s validator hard maximum unchanged | deterministic deadline fixtures |
| targeted SUCCESS without associated first-valid | generation-local target first-valid is mandatory before success | causality fixtures |
| APP_NOT_FOREGROUND ambiguous/duplicated | logical violation intervals with lifecycle/environment provenance | environment interval fixtures |
| short run could threaten evidence selection | frozen completed-run history remains selected/re-exportable | history fixtures |
