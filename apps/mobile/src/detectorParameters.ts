export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v4';
export const DETECTOR_PARAMETER_HASH = '9d111630f6109316b65650a5c119dbff2fdc990528d58826641d56b29fd9daa6';
export const DETECTOR_V4 = Object.freeze({
  minSamplesPerLink: 20, minObserverNodes: 3, minDirectionalLinks: 6, minPhysicalBaselines: 3,
  minOverlapMs: 1000, minMeanQuality: 0.45, humanThreshold: 0.58, noHumanThreshold: 0.28,
  disturbedLinkThreshold: 0.44, minDisturbedLinks: 2, minDisturbedBaselines: 2,
});
