// Generated from validation/fixtures/dev20_3/detector-parameter-manifest.json
export const DETECTOR_ALGORITHM = 'deterministic-multinode-rssi-fusion-v3';
export const DETECTOR_PARAMETER_HASH = 'f30d69c379ffb266581d6616fa4ad46b62fed40d9c0c643fb73ecf9cb4be0ccf';
export const DETECTOR = Object.freeze({
  minSamplesPerLink:20,minObserverNodes:3,minDirectionalLinks:6,minPhysicalBaselines:3,maxAlignmentSpanMs:12000,minMeanQuality:0.45,featureClip:4,
  humanSupportScore:0.66,humanMinDisturbedLinks:2,humanMinDisturbedBaselines:2,noHumanMaxScore:0.25,noHumanMaxDisturbedLinks:0,
  weights:{medianShift:.07,meanShift:.06,madChange:.08,varianceChange:.16,iqrChange:.12,derivativeEnergy:.18,slopeActivity:.10,deviationOccupancy:.12,persistence:.11},
  fusion:{reciprocalSupport:.16,crossLinkSupport:.18,observerSupport:.08,baselineSupport:.08}
});
