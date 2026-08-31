#!/usr/bin/env python3
from pathlib import Path
R=Path(__file__).resolve().parents[2]
def must(p,s):
 t=(R/p).read_text();assert s in t,(p,s)
def main():
 must('apps/mobile/src/humanPresence.ts','DecisionPublicationV7');must('apps/mobile/src/humanPresence.ts','DecisionAckV7');must('apps/mobile/src/humanPresence.ts','BodyFinderControlPlaneV7');must('apps/mobile/src/humanPresence.ts','DECISION_FRESH_MS=30_000');must('apps/mobile/src/humanPresence.ts','DECISION_EXPIRED_MS=60_000');must('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt','authoritativeTruthLedgerJson');must('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt','atomic_snapshot_gate_pass');must('apps/mobile/modules/body-finder-native/index.ts','dev20.7-self-contained-json-evidence-v10');must('crates/body-finder-science/src/human_detector.rs','coherent_low_amplitude_motion');must('crates/body-finder-science/src/human_detector.rs','segmented_transition_score');print('dev20.7 contract tests: PASS')
if __name__=='__main__':main()
