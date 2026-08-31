export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v8';
export const DETECTOR_PARAMETER_HASH = '5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39';
export const DETECTOR_V8 = Object.freeze({
  calibrationMinSamplesPerLink:30, observationMinSamplesPerLink:24, qualityReferenceSamples:24, minMeanQuality:0.80,
  calibrationMinOverlapMs:1500, inferenceMinOverlapMs:1500, minObserverNodes:3, minDirectionalLinks:6, minPhysicalBaselines:3,
  humanThreshold:0.50, noHumanThreshold:0.20, disturbedLinkThreshold:0.32, dynamicFloor:0.20,
  dynamicHumanLinkThreshold:0.55, persistenceHumanThreshold:0.34, coherentLowAmplitudeFusedFloor:0.26,
  coherentLowAmplitudeLinkFloor:0.20, coherentLowAmplitudeReciprocalFloor:0.70, coherentLowAmplitudeCrossLinkFloor:1/6,
  coherentLowAmplitudeBaselineFloor:1/3, segmentedTransitionFloor:0.18, burstActivityFloor:0.20,
  minDynamicLinks:3, minDynamicBaselines:2, negativeMaxFused:0.30, negativeMaxCrossLinkSupport:1/6,
  negativeMaxBaselineSupport:1/3, negativeMaxDynamicLinks:0, negativeMaxDynamicBaselines:0,
  observationWindowMs:60_000, transportEvidenceFreshMs:8_000, calibrationTimeoutMs:120_000,
  authorityPublicationLeaseMs:30_000, decisionFreshMs:30_000, decisionExpiryMs:60_000,
  membershipChangeGraceMs:45_000, coordinatorFailoverGraceMs:30_000, wireMaxDatagramBytes:1200, wireChunkPayloadBytes:640,
});
export const DETECTOR_V7 = DETECTOR_V8;
export const DETECTOR_V6 = DETECTOR_V8;
export const DETECTOR_V5 = DETECTOR_V8;
export const DETECTOR_V4 = DETECTOR_V8;
