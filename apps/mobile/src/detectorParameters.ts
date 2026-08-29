export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v5';
export const DETECTOR_PARAMETER_HASH = 'aaf97ff75573489ebc525a080e96ce09247b405f4c3d88136895c87263793b8e';
export const DETECTOR_V5 = Object.freeze({
  calibrationMinSamplesPerLink: 30,
  observationMinSamplesPerLink: 30,
  qualityReferenceSamples: 30,
  minMeanQuality: 0.90,
  calibrationMinOverlapMs: 1500,
  inferenceMinOverlapMs: 1000,
  minObserverNodes: 3,
  minDirectionalLinks: 6,
  minPhysicalBaselines: 3,
  humanThreshold: 0.58,
  noHumanThreshold: 0.30,
  disturbedLinkThreshold: 0.44,
  minDisturbedLinks: 2,
  minDisturbedBaselines: 2,
  dynamicFloor: 0.35,
  calibrationTimeoutMs: 60000,
  authorityPublicationLeaseMs: 15000,
  membershipChangeGraceMs: 12000,
});
export const DETECTOR_V4 = DETECTOR_V5; // compatibility alias; runtime contract is v5.
