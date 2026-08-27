#!/usr/bin/env python3
from __future__ import annotations
import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]

def repl(path,old,new):
    p=ROOT/path; text=p.read_text(encoding='utf-8')
    if new in text: return
    if old not in text: raise SystemExit(f'patch anchor missing: {path}: {old[:80]!r}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')

def main():
    (ROOT/'apps/mobile/src/version.ts').write_text("""export const RELEASE = Object.freeze({
  build: '0.2.0-experimental.20',
  reportVersion: 21,
  versionCode: 20,
  releaseIteration: 'experimental.20',
  protocolVersion: 2,
  snapshotSchemaVersion: 5,
  humanScanningEnabled: true,
  humanLocalizationValidated: false,
  rescueUseValidated: false,
});
export const BUILD = RELEASE.build;
export const REPORT_VERSION = RELEASE.reportVersion;
export const HUMAN_SCANNING_ENABLED = RELEASE.humanScanningEnabled;
""",encoding='utf-8')
    app=ROOT/'apps/mobile/app.json'; d=json.loads(app.read_text()); d['expo']['android']['versionCode']=20; d['expo']['extra']['releaseIteration']='experimental.20'; app.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
    n='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'
    repl(n,'    FabricEventTimeline.start(id, now, expectedPeerIdsAtStart)\n','    FabricEventTimeline.start(id, now, expectedPeerIdsAtStart)\n    HumanEvidenceTimeline.start(id, now)\n')
    repl(n,'    ValidationEventLog.record("VALIDATION_RUN_ENDED", id, now = now)\n    val base = liveDiagnostics(now, peerExpire, rebind, scanRestart, tx, rx)\n','    ValidationEventLog.record("VALIDATION_RUN_ENDED", id, now = now)\n    HumanEvidenceTimeline.end(now)\n    val base = liveDiagnostics(now, peerExpire, rebind, scanRestart, tx, rx)\n')
    repl(n,'      trimValidQueue(queue, now)\n','      trimValidQueue(queue, now)\n      HumanEvidenceTimeline.recordBle(FabricRuntime.nodeId, id, result.rssi, advertisedTx, now)\n')
    repl(n,'      .put("fabric_event_timeline", FabricEventTimeline.snapshot(now))\n','      .put("fabric_event_timeline", FabricEventTimeline.snapshot(now))\n      .put("human_evidence", HumanEvidenceTimeline.snapshot(now))\n')
    p=ROOT/n; p.write_text(p.read_text().replace('.put("snapshot_schema_version", 4)','.put("snapshot_schema_version", 5)'))
    u='apps/mobile/App.tsx'
    repl(u,"import { BUILD, REPORT_VERSION, HUMAN_SCANNING_ENABLED, RELEASE } from './src/version';\n","import { BUILD, REPORT_VERSION, HUMAN_SCANNING_ENABLED, RELEASE } from './src/version';\nimport { estimateHumanPresence } from './src/humanPresence';\n")
    repl(u,"    noTarget: 'Human scanning remains intentionally blocked until the experimental.16 validation-integrity gate is reviewed. This build validates sensor geometry acquisition continuity only.',\n","    noTarget: 'Presence-only experimental mode. A negative RF result is not proof that no person is present. Localization remains blocked until dev-21 physical acceptance.',\n")
    repl(u,"    noTarget: 'El escaneo humano permanece bloqueado intencionalmente hasta revisar el gate de continuidad de adquisición BLE de experimental.16. Esta build valida únicamente la continuidad de adquisición de la geometría de sensores.',\n","    noTarget: 'Modo experimental solo de presencia. Un resultado RF negativo no prueba ausencia de personas. La localización sigue bloqueada hasta la aceptación física dev-21.',\n")
    repl(u,'  const arrayTarget = useMemo(() => estimateHuman(geometryNodes, geometry), [geometryNodes, geometry]);\n','  const presence = useMemo(() => estimateHumanPresence(nodes), [nodes]);\n  const arrayTarget = useMemo(() => estimateHuman(geometryNodes, geometry), [geometryNodes, geometry]);\n')
    repl(u,'  const target = useMemo(() => relativeTarget(arrayTarget, localGeometry), [arrayTarget, localGeometry]);\n','  const target = useMemo(() => RELEASE.humanLocalizationValidated ? relativeTarget(arrayTarget, localGeometry) : null, [arrayTarget, localGeometry]);\n')
    repl(u,'      manual_geometry_override: false, human_scanning_enabled: HUMAN_SCANNING_ENABLED,\n','      manual_geometry_override: false, human_scanning_enabled: HUMAN_SCANNING_ENABLED,\n      human_presence_preview: presence,\n')
    repl(u,': <View style={s.card}><Text style={s.text}>{tx.noTarget}</Text></View>}',': <View style={s.card}><Text style={s.h2}>{scanning ? presence.prediction.replaceAll(\'_\', \' \') : \'PRESENCE SCAN IDLE\'}</Text><Text style={s.text}>{scanning ? `${tx.confidence}: ${(presence.human_confidence * 100).toFixed(0)}% · ${presence.evidence_quality}` : tx.noTarget}</Text><Text style={s.muted}>{scanning ? presence.reason : tx.evidence}</Text></View>}')
    cargo=ROOT/'crates/body-finder-science/Cargo.toml'; cargo.write_text(cargo.read_text().replace('version = "0.2.0-experimental.18"','version = "0.2.0-experimental.20"',1))
    print('dev20 source patches applied')
if __name__=='__main__':main()
