# ADR — Optional RTT/CSI/RuView capability truth

A modality reaches `VERIFIED_REAL` only after a runtime functional probe produces real samples. Phone model names are not evidence. Replay is labeled `REPLAY_ONLY`. CSI and RTT are optional and must fail open to the common BLE/RSSI path. Pixel 10 ranging stays `SUPPORTED_UNVERIFIED` while its real-result counter remains zero.
