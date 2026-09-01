#!/usr/bin/env python3
import pathlib
r=pathlib.Path(__file__).resolve().parents[2]
checks={'apps/mobile/src/version.ts':['0.2.0-experimental.20.11','reportVersion: 31','snapshotSchemaVersion: 14'],'apps/mobile/src/campaignControl.ts':['ScenarioCommandV1','RunFreezePrepareV1','SnapshotReadyV1','RunFreezeCommitV1'],'apps/mobile/src/humanPresence.ts':['BodyFinderControlPlaneV9','CalibrationPublicationV9','DecisionPublicationV9'],'apps/mobile/src/autogeometry.ts':['COORDINATOR_PUBLICATION_V11','GEOMETRY_PUBLICATION_HOLDOVER_MS'],'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt':['WireEnvelopeV10','WireTransportTelemetryV11','ArtifactManifestV3','max_control_bytes_by_key','GeometryPublicationV11']}
for p,xs in checks.items():
 s=(r/p).read_text()
 for x in xs:assert x in s,(p,x)
print('dev20.11 static contract PASS')
