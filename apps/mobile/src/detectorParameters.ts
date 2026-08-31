export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v7';
export const DETECTOR_PARAMETER_HASH = '7ff358bc4b1f92211e3a32d31285f5ab591c6fb79585c6b99814c1d0383d945d';
export const DETECTOR_V7 = Object.freeze({
  calibrationMinSamplesPerLink: 30,
  observationMinSamplesPerLink: 24,
  qualityReferenceSamples: 24,
  minMeanQuality: 0.80,
  calibrationMinOverlapMs: 1500,
  inferenceMinOverlapMs: 1500,
  minObserverNodes: 3,
  minDirectionalLinks: 6,
  minPhysicalBaselines: 3,
  humanThreshold: 0.50,
  noHumanThreshold: 0.20,
  disturbedLinkThreshold: 0.32,
  dynamicFloor: 0.20,
  dynamicHumanLinkThreshold: 0.55,
  persistenceHumanThreshold: 0.34,
  coherentLowAmplitudeFusedFloor: 0.26,
  coherentLowAmplitudeLinkFloor: 0.20,
  coherentLowAmplitudeReciprocalFloor: 0.70,
  coherentLowAmplitudeCrossLinkFloor: 1/6,
  coherentLowAmplitudeBaselineFloor: 1/3,
  segmentedTransitionFloor: 0.18,
  burstActivityFloor: 0.20,
  minDynamicLinks: 3,
  minDynamicBaselines: 2,
  observationWindowMs: 60_000,
  transportEvidenceFreshMs: 8_000,
  calibrationTimeoutMs: 120_000,
  authorityPublicationLeaseMs: 30_000,
  decisionFreshMs: 30_000,
  decisionExpiryMs: 60_000,
  membershipChangeGraceMs: 45_000,
  coordinatorFailoverGraceMs: 30_000,
});
export const DETECTOR_V6 = DETECTOR_V7;
export const DETECTOR_V5 = DETECTOR_V7;
export const DETECTOR_V4 = DETECTOR_V7;
