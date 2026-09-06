#!/usr/bin/env python3
"""Apply the dev-20.19 control-budget/evidence remediation idempotently."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"missing expected marker: {label}")
    return text.replace(old, new)


def patch_human_presence() -> None:
    rel = "apps/mobile/src/humanPresence.ts"
    t = read(rel)
    if "CalibrationMetaWireV4" not in t:
        pattern = re.compile(
            r"function publicationFrom\(nodes:Advertisement\[],coordinatorNodeId:string\|null\)\{.*?\}\n"
            r"function calibrationMetaWire\(\)\{.*?\}\n"
            r"(?=function calibrationAckWire)",
            re.S,
        )
        replacement = """function publicationFrom(nodes:Advertisement[],coordinatorNodeId:string|null){const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const raw=(coordinator?.control_plane as any)?.calibration_meta_v10??null;if(raw?.schema==='CalibrationMetaWireV4')return{schema:'CalibrationMetaWireV4',session_id:String(coordinator?.session_id??''),coordinator_id:String(coordinator?.node_id??''),cg:Number(raw.cg),g:Number(raw.g),id:raw.i,hash:raw.h,artifact_id:String(raw.a??`calibration:${raw.i}`),artifact_sha256:String(raw.x??''),topology_hash:raw.t,seq:Number(raw.q),lease_ms:Number(raw.l),authority_digest:raw.d};return raw}\nfunction calibrationMetaWire(){if(!cal.artifact||!cal.coordinator)return null;const topology_hash=assertCanonicalTopologyHash(canonicalTopologyHash()),artifactSha=BodyFinderNative.sha256Text(canonicalArtifact(cal.artifact));return{schema:'CalibrationMetaWireV4',cg:cal.coordinatorGeneration,g:cal.generation,i:cal.artifact.calibration_id,a:`calibration:${cal.artifact.calibration_id}`,x:artifactSha,h:cal.artifact.calibration_hash,t:topology_hash,q:cal.publicationSequence,l:DETECTOR_V8.authorityPublicationLeaseMs,d:cal.authorityDigest}}\n"""
        t2, count = pattern.subn(replacement, t, count=1)
        if count != 1:
            raise RuntimeError(f"expected one calibration meta encoder block, got {count}")
        t = t2
    t = t.replace("p?.schema==='CalibrationMetaWireV3'", "p?.schema==='CalibrationMetaWireV4'")
    # Dev-20.19 intentionally does not accept V3 metadata. Mixed dev-20.18/dev-20.19 cohorts fail closed.
    write(rel, t)


def patch_version() -> None:
    rel = "apps/mobile/src/version.ts"
    t = read(rel)
    t = t.replace("0.2.0-experimental.20.18", "0.2.0-experimental.20.19")
    t = t.replace("reportVersion: 38", "reportVersion: 39")
    t = t.replace("versionCode: 38", "versionCode: 39")
    t = t.replace("releaseIteration: 'experimental.20.18'", "releaseIteration: 'experimental.20.19'")
    t = t.replace("snapshotSchemaVersion: 20", "snapshotSchemaVersion: 21")
    write(rel, t)


def patch_registry() -> None:
    rel = "apps/mobile/src/criticalControlRegistry.ts"
    t = read(rel)
    old = "export const CRITICAL_CONTROL_BUDGET=Object.freeze({payloadBytes:600,frameBytes:900,datagramBytes:1200});"
    new = "export const CRITICAL_CONTROL_BUDGET=Object.freeze({payloadBytes:600,calibrationMetaEngineeringTargetBytes:560,frameBytes:900,datagramBytes:1200});"
    t = replace_required(t, old, new, "critical control engineering target")
    write(rel, t)


def patch_app() -> None:
    rel = "apps/mobile/App.tsx"
    t = read(rel)
    t = t.replace("release:'dev-20.17',build:BUILD,evidence_schema:'v19'", "release:'dev-20.19',build:BUILD,evidence_schema:'v21',artifact_build_identity:`dev-20.19:${BUILD}`")
    old = "const serialized=BodyFinderNative.exportPreRunDiagnosticJson(JSON.stringify(context));const fn=`pre-run-diagnostic-dev20.17-${String(local?.node_id??'node').slice(-8)}.json`;"
    new = "const rawSerialized=BodyFinderNative.exportPreRunDiagnosticJson(JSON.stringify(context));const normalized=JSON.parse(rawSerialized);Object.assign(normalized,{release:'dev-20.19',build:BUILD,evidence_schema:'v21',report_version:REPORT_VERSION,snapshot_schema_version:RELEASE.snapshotSchemaVersion,artifact_build_identity:`dev-20.19:${BUILD}`,evidence_contract_version:'dev20.19-state-lifecycle-json-evidence-v21'});normalized.diagnostic_contract={...(normalized.diagnostic_contract??{}),schema:'dev20.19-diagnostic-contract-v21'};normalized.evidence_contract={...(normalized.evidence_contract??{}),schema:'dev20.19-state-lifecycle-json-evidence-v21'};const serialized=JSON.stringify(normalized,null,2);const fn=`pre-run-diagnostic-dev20.19-${String(local?.node_id??'node').slice(-8)}.json`;"
    t = replace_required(t, old, new, "PRE_RUN normalization")
    t = t.replace("fresh?.wire_transport_v13?.artifact_peer_state_v1??fresh?.wire_transport?.artifact_peer_state_v1??null", "fresh?.fabric_diagnostics?.wire_transport_v11?.artifact_peer_state_v1??null")
    t = t.replace("fresh?.wire_transport_v13?.artifact_receiver_state_v1??fresh?.wire_transport?.artifact_receiver_state_v1??null", "fresh?.fabric_diagnostics?.wire_transport_v11?.artifact_receiver_state_v1??null")
    t = t.replace("fresh?.wire_transport_v13??fresh?.wire_transport??null", "fresh?.fabric_diagnostics?.wire_transport_v11??null")
    t = t.replace("schema: 'dev20.10-self-contained-json-evidence-v13'", "schema: 'dev20.19-state-lifecycle-json-evidence-v21'")
    t = t.replace("schema:'dev20.10-diagnostic-contract-v13'", "schema:'dev20.19-diagnostic-contract-v21'")
    marker = "report_version: REPORT_VERSION,\n      generated_at: new Date().toISOString(), app: 'Body Finder – RuView', build: BUILD, protocol_version: 2,"
    replacement = "report_version: REPORT_VERSION, release: 'dev-20.19', evidence_schema: 'v21', snapshot_schema_version: RELEASE.snapshotSchemaVersion, artifact_build_identity: `dev-20.19:${BUILD}`,\n      generated_at: new Date().toISOString(), app: 'Body Finder – RuView', build: BUILD, protocol_version: 2,"
    t = replace_required(t, marker, replacement, "acceptance identity")
    t = t.replace("acceptance ≥300s", "acceptance ≥330s")
    write(rel, t)


def patch_native_contract() -> None:
    rel = "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
    t = read(rel)
    t = t.replace('.put("report_version", 37)', '.put("report_version", 39)')
    t = t.replace('.put("snapshot_schema_version", 16)', '.put("snapshot_schema_version", 21)')
    t = t.replace("dev20.15-self-contained-json-evidence-v17", "dev20.19-state-lifecycle-json-evidence-v21")
    write(rel, t)


def patch_package_metadata() -> None:
    candidates = [
        "apps/mobile/package.json",
        "apps/mobile/package-lock.json",
        "apps/mobile/app.json",
        "apps/android-legacy/app/build.gradle",
        "apps/android-legacy/app/build.gradle.kts",
    ]
    for rel in candidates:
        p = ROOT / rel
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        t = t.replace("0.2.0-experimental.20.18", "0.2.0-experimental.20.19")
        t = t.replace("0.2.0~experimental20.18", "0.2.0~experimental20.19")
        if rel.endswith("app.json"):
            t = t.replace('"versionCode": 38', '"versionCode": 39')
        p.write_text(t, encoding="utf-8")


def main() -> None:
    patch_human_presence()
    patch_version()
    patch_registry()
    patch_app()
    patch_native_contract()
    patch_package_metadata()
    hp = read("apps/mobile/src/humanPresence.ts")
    assert "CalibrationMetaWireV4" in hp
    assert "calibration_artifact_id:`calibration:" not in hp
    assert "artifact_sha256:String(raw.x??'')" in hp
    print("DEV20_19_REMEDIATION_APPLIED")


if __name__ == "__main__":
    main()
