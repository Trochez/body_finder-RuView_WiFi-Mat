export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v6';
export const DETECTOR_PARAMETER_HASH = '0fdb8a3b9ae003cc6d138c970ecdc0237bc2186b440e5469763e2d6c2e49f2f1';
export const DETECTOR_V6 = Object.freeze({
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
  noHumanThreshold: 0.27,
  disturbedLinkThreshold: 0.32,
  dynamicFloor: 0.20,
  dynamicHumanLinkThreshold: 0.55,
  persistenceHumanThreshold: 0.34,
  minDynamicLinks: 3,
  minDynamicBaselines: 2,
  observationWindowMs: 60_000,
  transportEvidenceFreshMs: 8_000,
  calibrationTimeoutMs: 120_000,
  authorityPublicationLeaseMs: 30_000,
  membershipChangeGraceMs: 45_000,
  coordinatorFailoverGraceMs: 30_000,
});
export const DETECTOR_V5 = DETECTOR_V6; // compatibility alias; runtime contract is v6.
export const DETECTOR_V4 = DETECTOR_V6;
