#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(path): return (ROOT/path).read_text()
def write(path,text):
    target=ROOT/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(text)
def once(text,old,new,label):
    count=text.count(old)
    if count!=1: raise RuntimeError(f'{label}: expected 1 match, got {count}')
    return text.replace(old,new,1)

# Version only: protocol and snapshot schema stay unchanged.
p='apps/mobile/src/version.ts'; text=read(p).replace('0.2.0-experimental.14','0.2.0-experimental.15').replace('reportVersion: 16','reportVersion: 17').replace('versionCode: 14','versionCode: 15').replace("releaseIteration: 'experimental.14'","releaseIteration: 'experimental.15'"); write(p,text)
p='apps/mobile/app.json'; text=read(p).replace('"versionCode": 14','"versionCode": 15').replace('"releaseIteration": "experimental.14"','"releaseIteration": "experimental.15"'); write(p,text)

# Recovery FIRST_VALID accounting is observational only.
p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt'; text=read(p).replace('Acquisition-only policy for experimental.14.','Acquisition-only policy for experimental.15.')
text=once(text,'  @Volatile private var firstValidCallbackWallMs: Long? = null\n','  @Volatile private var firstValidCallbackWallMs: Long? = null\n  @Volatile private var firstValidCallbackCountTotal: Long = 0L\n','first valid declaration')
text=once(text,'    firstValidCallbackWallMs = null\n    lastRecoveryLatencyMs = null\n','    firstValidCallbackWallMs = null\n    firstValidCallbackCountTotal = 0L\n    lastRecoveryLatencyMs = null\n','first valid reset')
text=once(text,'  fun firstValidRecoveryWallMs(): Long? = firstValidCallbackWallMs\n','  fun firstValidRecoveryWallMs(): Long? = firstValidCallbackWallMs\n  fun firstValidRecoveryCallbackCount(): Long = firstValidCallbackCountTotal\n','first valid getter')
text=once(text,'    firstValidCallbackWallMs = now\n    ValidationEventLog.record(\n','    firstValidCallbackWallMs = now\n    firstValidCallbackCountTotal++\n    ValidationEventLog.record(\n','first valid increment'); write(p,text)

p='apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt'; text=read(p)
text=once(text,'private data class PeerStarvationCounterSnapshot(\n  val starvationCount: Long,\n  val recoveryParticipationCount: Long,\n  val recoverySuccessCount: Long,\n  val recoveryFailureCount: Long,\n)','private data class PeerStarvationCounterSnapshot(\n  val starvationCount: Long,\n  val recoveryParticipationCount: Long,\n  val firstValidCallbackCount: Long,\n  val recoverySuccessCount: Long,\n  val recoveryFailureCount: Long,\n)','peer snapshot')
text=once(text,'  @Volatile private var baselineRecoveryAttempts: Long = 0\n','  @Volatile private var baselineRecoveryAttempts: Long = 0\n  @Volatile private var baselineFirstValidCallbacks: Long = 0\n','global baseline')
text=once(text,'    baselineRecoveryAttempts = BleAcquisitionPolicy.recoveryAttemptCount()\n','    baselineRecoveryAttempts = BleAcquisitionPolicy.recoveryAttemptCount()\n    baselineFirstValidCallbacks = BleAcquisitionPolicy.firstValidRecoveryCallbackCount()\n','global baseline capture')
text=once(text,'      .put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))\n','      .put("recovery_attempt_delta", (BleAcquisitionPolicy.recoveryAttemptCount() - baselineRecoveryAttempts).coerceAtLeast(0))\n      .put("recovery_first_valid_callback_delta", (BleAcquisitionPolicy.firstValidRecoveryCallbackCount() - baselineFirstValidCallbacks).coerceAtLeast(0))\n','live global first valid')
text=once(text,'      .put("recovery_attempt_delta", base.optLong("recovery_attempt_delta"))\n','      .put("recovery_attempt_delta", base.optLong("recovery_attempt_delta"))\n      .put("recovery_first_valid_callback_delta", base.optLong("recovery_first_valid_callback_delta"))\n','frozen global first valid')
text=once(text,'  val peerStarvationRecoveryParticipationByPeer = ConcurrentHashMap<String, AtomicLong>()\n','  val peerStarvationRecoveryParticipationByPeer = ConcurrentHashMap<String, AtomicLong>()\n  val peerStarvationRecoveryFirstValidByPeer = ConcurrentHashMap<String, AtomicLong>()\n','peer first valid map')
text=once(text,'    peerStarvationRecoveryParticipationByPeer.clear()\n','    peerStarvationRecoveryParticipationByPeer.clear()\n    peerStarvationRecoveryFirstValidByPeer.clear()\n','peer first valid clear')
text=once(text,'        peerStarvationCountByPeer[peerId]?.get() ?: 0,\n        peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0,\n        peerStarvationRecoverySuccessByPeer[peerId]?.get() ?: 0,\n        peerStarvationRecoveryFailureByPeer[peerId]?.get() ?: 0,','        peerStarvationCountByPeer[peerId]?.get() ?: 0,\n        peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0,\n        peerStarvationRecoveryFirstValidByPeer[peerId]?.get() ?: 0,\n        peerStarvationRecoverySuccessByPeer[peerId]?.get() ?: 0,\n        peerStarvationRecoveryFailureByPeer[peerId]?.get() ?: 0,','peer baseline capture')
text=once(text,'    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {\n      BleAcquisitionPolicy.noteRecoveryFirstValidCallback(now, callbackPeerId)\n    }','    if (validRssi && BleAcquisitionPolicy.currentStrategy() == BleAcquisitionStrategy.UNFILTERED_RECOVERY) {\n      val acceptedFirstValid = BleAcquisitionPolicy.noteRecoveryFirstValidCallback(now, callbackPeerId)\n      if (acceptedFirstValid && callbackPeerId != null && BleAcquisitionPolicy.activeRecoveryTriggerKind() == RecoveryTriggerKind.PEER_STARVATION) {\n        FabricRuntime.peerStarvationRecoveryFirstValidByPeer.computeIfAbsent(callbackPeerId) { AtomicLong(0) }.incrementAndGet()\n      }\n    }','accepted first valid')
text=once(text,'          put("starvation_recovery_participation_count", FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0)\n','          put("starvation_recovery_participation_count", FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0)\n          put("first_callback_after_recovery_count", FabricRuntime.peerStarvationRecoveryFirstValidByPeer[peerId]?.get() ?: 0)\n','peer lifetime first valid')
text=once(text,'          put("run_starvation_recovery_participation_count", starvationDelta(FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoveryParticipationCount))\n','          put("run_starvation_recovery_participation_count", starvationDelta(FabricRuntime.peerStarvationRecoveryParticipationByPeer[peerId]?.get() ?: 0, starvationBaseline?.recoveryParticipationCount))\n          put("run_first_callback_after_recovery_count", starvationDelta(FabricRuntime.peerStarvationRecoveryFirstValidByPeer[peerId]?.get() ?: 0, starvationBaseline?.firstValidCallbackCount))\n','peer run first valid'); write(p,text)

# Self-identifying evidence metadata. Stage is inferred from selected frozen run/history, never filename.
p='apps/mobile/App.tsx'; text=read(p).replace('experimental.14','experimental.15')
text=once(text,'  const validationActionLock = useRef(false);\n','  const validationActionLock = useRef(false);\n  const exportSequenceByRun = useRef<Record<string, number>>({});\n','export sequence ref')
old='    try { calibrationSnapshot = JSON.parse(BodyFinderNative.getCalibrationSnapshotJson()); } catch {}\n    const payload = {'
new='''    try { calibrationSnapshot = JSON.parse(BodyFinderNative.getCalibrationSnapshotJson()); } catch {}
    const selectedRun = freshDiagnostics?.validation_run ?? null;
    const selectedRunId = typeof selectedRun?.run_id === 'string' ? selectedRun.run_id : 'no-run';
    const exportSequence = (exportSequenceByRun.current[selectedRunId] ?? 0) + 1;
    exportSequenceByRun.current[selectedRunId] = exportSequence;
    const completedRuns = Array.isArray(freshDiagnostics?.completed_validation_runs_summary) ? freshDiagnostics.completed_validation_runs_summary : [];
    const runType = selectedRun?.short_diagnostic_run === true ? 'SHORT' : 'LONG';
    const runEnded = typeof selectedRun?.ended_wall_ms === 'number' ? selectedRun.ended_wall_ms : 0;
    const laterShort = runType === 'LONG' && completedRuns.some((run: any) => run?.short_diagnostic_run === true && typeof run?.ended_wall_ms === 'number' && run.ended_wall_ms > runEnded);
    const snapshotStage = runType === 'SHORT' ? 'SHORT' : laterShort ? 'LONG_POST_SHORT' : exportSequence === 1 ? 'LONG_1' : 'LONG_2';
    const priorLong = completedRuns.filter((run: any) => run?.short_diagnostic_run === false && typeof run?.ended_wall_ms === 'number' && run.ended_wall_ms <= runEnded).sort((x: any, y: any) => (x.ended_wall_ms ?? 0) - (y.ended_wall_ms ?? 0)).at(-1);
    const sourceLongRunId = runType === 'SHORT' ? priorLong?.run_id ?? null : selectedRunId;
    const deviceAlias = String(caps?.model ?? local?.display_name ?? 'android-device').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const suggestedFilename = `${deviceAlias}-${selectedRunId.slice(0, 8)}-${snapshotStage.toLowerCase().replaceAll('_', '-')}.json`;
    const payload = {'''
text=once(text,old,new,'export metadata prelude')
old="      report_version: REPORT_VERSION,\n      generated_at: new Date().toISOString(), app: 'Body Finder – RuView', build: BUILD, protocol_version: 2,"
new="""      report_version: REPORT_VERSION,
      generated_at: new Date().toISOString(), app: 'Body Finder – RuView', build: BUILD, protocol_version: 2,
      json_self_contained: true, screenshots_required: false,
      export_metadata: {
        device_alias: deviceAlias, device_manufacturer: caps?.manufacturer ?? null, device_model: caps?.model ?? null,
        node_id: local?.node_id ?? null, run_id: selectedRunId, run_type: runType, snapshot_stage: snapshotStage,
        elapsed_ms: selectedRun?.elapsed_ms ?? null, snapshot_frozen: selectedRun?.snapshot_frozen ?? false,
        source_long_run_id: sourceLongRunId, export_sequence: exportSequence, generated_at: new Date().toISOString(),
        build: BUILD, protocol_version: 2, suggested_filename: suggestedFilename,
      },"""
text=once(text,old,new,'metadata object').replace("schema: 'dev14-self-contained-json-evidence-v3'","schema: 'dev15-self-contained-json-evidence-v3'")
text=once(text,"    await Share.share({ message: JSON.stringify(payload, null, 2), title: 'Body Finder experimental.15 self-contained validation result' });","    await Share.share({ message: JSON.stringify(payload, null, 2), title: suggestedFilename });",'share title'); write(p,text)

# Release pipeline: derive from working dev14 pipeline, but canonicalize assets and checksum verification.
rel=read('.github/workflows/release-exp14.yml').replace('experimental.14','experimental.15').replace('experimental14','experimental15').replace('dev14','dev15').replace('Dev14','Dev15').replace('DEV14','DEV15').replace('"versionCode": 14','"versionCode": 15').replace("'schema_version':14","'schema_version':15").replace('BodyFinder-dev14-universal.apk','BodyFinder-dev15-universal.apk')
old='''          python3 validation/android/check_dev15_environment_contract.py
          python3 validation/android/check_dev15_recovery_contract.py
          python3 validation/android/test_dev15_recovery_model.py
          python3 validation/analysis/validate_environment_authorization.py
          python3 validation/analysis/validate_dev15_fixture_matrix.py
          python3 -m py_compile validation/analysis/validate_dev15_hard_gates.py validation/analysis/dev15_validation.py validation/analysis/validate_environment_intervals.py validation/analysis/validate_timeline_causality.py validation/analysis/validate_peer_starvation_recovery.py validation/analysis/calculate_accuracy_report.py validation/analysis/build_acceptance_report.py validation/analysis/validate_release_manifest.py'''
new='''          python3 scripts/generate_dev15_fixtures.py
          python3 validation/android/check_dev15_frozen_truth_contract.py
          python3 validation/analysis/test_dev15_tooling.py
          python3 -m py_compile validation/analysis/dev15_validation.py validation/analysis/validate_dev15_acceptance.py validation/analysis/validate_dev15_hard_gates.py validation/analysis/calculate_accuracy_report.py validation/analysis/build_acceptance_report.py validation/analysis/test_dev15_tooling.py validation/analysis/validate_release_manifest.py'''
rel=once(rel,old,new,'release requirements')
rel=rel.replace("          printf '{\"method\":\"tape\",\"ground_truth_entered_into_app\":false,\"pairs_m\":{\"pixel10|pixel7\":null,\"pixel10|lenovo\":null,\"pixel7|lenovo\":null}}\\n' > dist/ground-truth-template.json","          cp validation/ground-truth/GROUND_TRUTH_TEMPLATE.json dist/GROUND_TRUTH_TEMPLATE.json")
old='''          mkdir kit
          cp validation/analysis/*.py validation/android/check_*.py kit/
          cp protocol/schemas/validation-run-snapshot-v3.json kit/
          cp docs/TESTING_DEV15.md kit/
          (cd kit && zip -r ../dist/body-finder-validation-tools.zip .)
          cp dist/body-finder-validation-tools.zip dist/validators-dev15.zip
          (cd validation/fixtures/dev15 && zip -r "$GITHUB_WORKSPACE/dist/fixtures-dev15.zip" .)'''
new='''          mkdir -p kit/validation/fixtures/dev15
          cp validation/analysis/*.py validation/android/check_dev15_frozen_truth_contract.py kit/
          cp protocol/schemas/validation-run-snapshot-v3.json kit/
          cp docs/TESTING_DEV15.md kit/
          cp -r validation/fixtures/dev15/* kit/validation/fixtures/dev15/
          (cd kit && zip -r ../dist/validators-dev15.zip .)
          (cd validation/fixtures/dev15 && zip -r "$GITHUB_WORKSPACE/dist/fixtures-dev15.zip" .)
          rm -f dist/ruvview-upstream-lock.json'''
rel=once(rel,old,new,'release validation kit')
rel=rel.replace(' body-finder-validation-tools.zip','').replace(' ground-truth-template.json',' GROUND_TRUTH_TEMPLATE.json')
rel=rel.replace("          (cd dist && sha256sum * > SHA256SUMS.txt)","          (cd dist && find . -maxdepth 1 -type f ! -name SHA256SUMS.txt -printf '%f\\n' | sort | xargs sha256sum > SHA256SUMS.txt)")
rel=rel.replace("          printf '{\"release\":\"dev-15\",\"pass\":true,\"checksums_verified\":true,\"screenshots_required\":false}\\n' > dist/release-verification.json","          printf '{\"release\":\"dev-15\",\"pass\":true,\"checksums_verified\":true,\"screenshots_required\":false,\"physical_smoke_required\":true,\"physical_smoke_status\":\"PENDING_USER_HARDWARE\"}\\n' > dist/release-verification.json")
rel=rel.replace("          gh release upload dev-15 verify/release-verification.json --clobber","          (cd verify && find . -maxdepth 1 -type f ! -name SHA256SUMS.txt -printf '%f\\n' | sort | xargs sha256sum > SHA256SUMS.txt)\n          gh release upload dev-15 verify/release-verification.json verify/SHA256SUMS.txt --clobber")
write('.github/workflows/release-exp15.yml',rel)
write('RELEASE_DEV15_TRIGGER.txt','dev-15 release trigger generated by apply_dev15_android_release.py\n')
print('DEV15_ANDROID_RELEASE_MATERIALIZED')
