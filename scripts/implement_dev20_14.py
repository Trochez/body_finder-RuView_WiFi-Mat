#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement, found {count}: {old[:80]!r}")
    write(path, text.replace(old, new, 1))


AUTHORITY_TS = r'''import BodyFinderNative from '../modules/body-finder-native';
import { Advertisement } from './autogeometry';

export type AuthorityCohortMember={node_id:string;instance_epoch:string};
export type AuthorityViewV1={schema:'AuthorityViewV1';session_id:string;cohort:AuthorityCohortMember[];elected_coordinator:string;coordinator_generation:number;base_digest:string;authority_view_digest:string};
export type AuthorityWireV2={schema:'AuthorityWireV2';s:string;e:string;g:number;b:string;d:string};
export type AuthorityAckWireV2={schema:'AuthorityAckWireV2';s:string;n:string;e:string;g:number;b:string;d:string};
type PeerCommitment={schema:'AuthorityWireV2'|'AuthorityViewV1';session_id:string;elected_coordinator:string;coordinator_generation:number;base_digest:string;authority_view_digest:string};
type State={baseDigest:string|null;generation:number;pinned:boolean;pinnedView:AuthorityViewV1|null};
const states=new Map<string,State>();
function canonical(v:any):string{if(v===null||typeof v!=='object')return JSON.stringify(v);if(Array.isArray(v))return'['+v.map(canonical).join(',')+']';return'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}'}
function sha(v:unknown){return BodyFinderNative.sha256Text(typeof v==='string'?v:canonical(v))}
function currentSession(nodes:Advertisement[]){const c=new Map<string,number>();for(const n of nodes){if(n.protocol_version===2&&n.session_id)c.set(String(n.session_id),(c.get(String(n.session_id))??0)+1)}return[...c.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))[0]?.[0]??'body-finder-lab'}
function live(nodes:Advertisement[],sid:string){return nodes.filter(n=>n.protocol_version===2&&String(n.session_id)===sid&&Boolean(n.node_id)&&Number((n as any).membership_lease_age_ms??0)<=15_000&&String((n as any).membership_lease_state??'LIVE')!=='EXPIRED')}
function epochOf(n:Advertisement){const e=String((n as any).instance_epoch??'').trim();return e&&e!=='legacy'?e:null}
function completeCohort(nodes:Advertisement[],sid:string){const by=new Map<string,Advertisement[]>();for(const n of live(nodes,sid)){const id=String(n.node_id),epoch=epochOf(n);if(!epoch)continue;by.set(id,[...(by.get(id)??[]),n])}if(by.size!==3)return null;const selected=[...by.entries()].map(([,items])=>items.sort((a,b)=>Number((a as any).membership_lease_age_ms??0)-Number((b as any).membership_lease_age_ms??0)||String(epochOf(a)).localeCompare(String(epochOf(b))))[0]);return selected.sort((a,b)=>String(a.node_id).localeCompare(String(b.node_id))||String(epochOf(a)).localeCompare(String(epochOf(b))))}
function state(sid:string){let s=states.get(sid);if(!s){s={baseDigest:null,generation:0,pinned:false,pinnedView:null};states.set(sid,s)}return s}
function commitment(v:any):PeerCommitment|undefined{if(v?.schema==='AuthorityWireV2'&&typeof v.s==='string'&&typeof v.e==='string'&&Number.isFinite(Number(v.g))&&typeof v.b==='string'&&typeof v.d==='string')return{schema:'AuthorityWireV2',session_id:v.s,elected_coordinator:v.e,coordinator_generation:Number(v.g),base_digest:v.b,authority_view_digest:v.d};if(v?.schema==='AuthorityViewV1'&&typeof v.session_id==='string'&&typeof v.elected_coordinator==='string'&&Number.isFinite(Number(v.coordinator_generation))&&typeof v.base_digest==='string'&&typeof v.authority_view_digest==='string')return{schema:'AuthorityViewV1',session_id:v.session_id,elected_coordinator:v.elected_coordinator,coordinator_generation:Number(v.coordinator_generation),base_digest:v.base_digest,authority_view_digest:v.authority_view_digest};return undefined}
function peerCommitments(nodes:Advertisement[]){return nodes.map(n=>commitment((n.control_plane as any)?.authority_view_v1)).filter((v):v is PeerCommitment=>Boolean(v))}
function encodeView(v:AuthorityViewV1):AuthorityWireV2{return{schema:'AuthorityWireV2',s:v.session_id,e:v.elected_coordinator,g:v.coordinator_generation,b:v.base_digest,d:v.authority_view_digest}}
function compute(nodes:Advertisement[]):AuthorityViewV1|null{const sid=currentSession(nodes),s=state(sid);if(s.pinned&&s.pinnedView)return s.pinnedView;const cohortNodes=completeCohort(nodes,sid);if(!cohortNodes)return null;const cohort=cohortNodes.map(n=>({node_id:String(n.node_id),instance_epoch:epochOf(n)!}));const elected=[...cohortNodes].sort((a,b)=>Number(b.coordinator_score??0)-Number(a.coordinator_score??0)||String(a.node_id).localeCompare(String(b.node_id))||String(epochOf(a)).localeCompare(String(epochOf(b))))[0]?.node_id;if(!elected)return null;const base={session_id:sid,cohort,elected_coordinator:String(elected)},baseDigest=sha(base),views=peerCommitments(nodes).filter(v=>v.session_id===sid),same=views.filter(v=>v.base_digest===baseDigest&&v.elected_coordinator===String(elected));if(s.baseDigest!==baseDigest){if(same.length){s.generation=Math.max(1,...same.map(v=>v.coordinator_generation))}else{const maxObserved=Math.max(s.generation,0,...views.map(v=>v.coordinator_generation));s.generation=(s.baseDigest!==null||views.length>0)?Math.max(1,maxObserved+1):1}s.baseDigest=baseDigest}else{s.generation=Math.max(s.generation,1,...same.map(v=>v.coordinator_generation))}const material={...base,coordinator_generation:s.generation},view:AuthorityViewV1={schema:'AuthorityViewV1',...material,base_digest:baseDigest,authority_view_digest:sha(material)};const committed=nodes.some(n=>{const c=(n.control_plane as any)?.run_start_commit_v1;return c?.schema==='RunStartCommitV1'&&c?.authority_view_digest===view.authority_view_digest});if(committed){s.pinned=true;s.pinnedView=view}return view}
function epochBlocker(nodes:Advertisement[],sid:string){const current=live(nodes,sid),ids=[...new Set(current.map(n=>String(n.node_id)))];return ids.length===3&&current.some(n=>!epochOf(n))}
export function getAuthorityStatus(nodes:Advertisement[],localNodeId:string|null){const sid=currentSession(nodes),view=compute(nodes);if(!view)return{schema:'AuthorityStatusV2',view:null,canonical_cohort_input:[],ack_matrix:[],ack_count:0,consensus:false,blocking_reasons:[epochBlocker(nodes,sid)?'AUTHORITY_INSTANCE_EPOCH_UNINITIALIZED':'AUTHORITY_COHORT_INCOMPLETE']};const ids=view.cohort.map(x=>x.node_id);const ack_matrix=ids.map(id=>{if(id===localNodeId)return{node_id:id,acknowledged:true,authority_view_digest:view.authority_view_digest};const cp=(nodes.find(n=>n.node_id===id)?.control_plane as any),rawView=cp?.authority_view_v1,pv=commitment(rawView),pa=cp?.authority_ack_v1;const viewOk=rawView?.schema==='AuthorityWireV2'&&pv?.session_id===view.session_id&&pv?.elected_coordinator===view.elected_coordinator&&pv?.coordinator_generation===view.coordinator_generation&&pv?.base_digest===view.base_digest&&pv?.authority_view_digest===view.authority_view_digest;const ackOk=pa?.schema==='AuthorityAckWireV2'&&pa?.s===view.session_id&&pa?.n===id&&pa?.e===view.elected_coordinator&&Number(pa?.g)===view.coordinator_generation&&pa?.b===view.base_digest&&pa?.d===view.authority_view_digest;return{node_id:id,acknowledged:Boolean(viewOk&&ackOk),authority_view_digest:pa?.d??pa?.authority_view_digest??null}});const ack_count=ack_matrix.filter(x=>x.acknowledged).length,consensus=ids.length===3&&ack_count===3;return{schema:'AuthorityStatusV2',view,canonical_cohort_input:view.cohort,base_digest:view.base_digest,authority_view_digest:view.authority_view_digest,coordinator_generation:view.coordinator_generation,ack_matrix,ack_count,consensus,blocking_reasons:consensus?[]:['AUTHORITY_ACK_3_OF_3_REQUIRED']}}
export function getAuthorityControlPublication(nodes:Advertisement[],localNodeId:string|null){const status=getAuthorityStatus(nodes,localNodeId),view=status.view;const ack:AuthorityAckWireV2|null=view&&localNodeId&&view.cohort.some(x=>x.node_id===localNodeId)?{schema:'AuthorityAckWireV2',s:view.session_id,n:localNodeId,e:view.elected_coordinator,g:view.coordinator_generation,b:view.base_digest,d:view.authority_view_digest}:null;return{authority_view_v1:view?encodeView(view):null,authority_ack_v1:ack}}
export function deterministicCoordinator(nodes:Advertisement[],localNodeId:string|null){return getAuthorityStatus(nodes,localNodeId).view?.elected_coordinator??null}
'''

write("apps/mobile/src/authority.ts", AUTHORITY_TS)

# Native process identity is generated once per startFabric. Ensure the exact same epoch
# is exported in the local advertisement and therefore in HEARTBEAT frames.
replace_once(
    "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt",
    '    put("node_id", FabricRuntime.nodeId)\n    put("display_name", FabricRuntime.displayName)',
    '    put("node_id", FabricRuntime.nodeId)\n    put("instance_epoch", FabricRuntime.instanceEpoch)\n    put("display_name", FabricRuntime.displayName)',
)
replace_once(
    "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt",
    '.put("report_version",33).put("snapshot_schema_version",16)',
    '.put("report_version",34).put("snapshot_schema_version",16)',
)
replace_once(
    "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt",
    '      .put("diagnostic_contract", JSONObject()',
    '      .put("local_instance_epoch_source", "FabricRuntime.instanceEpoch")\n      .put("local_instance_epoch", FabricRuntime.instanceEpoch)\n      .put("diagnostic_contract", JSONObject()',
)
# Contract name changes because PRE_RUN now guarantees canonical epoch provenance.
native_path = "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
native = read(native_path).replace("dev20.10-self-contained-json-evidence-v13", "dev20.14-self-contained-json-evidence-v17")
write(native_path, native)

# Remove all live membership fallback to the legacy placeholder. Election remains blocked
# until the process epoch is actually observed.
replace_once(
    "apps/mobile/src/humanPresence.ts",
    "for(const n of freshNodes(nodes,sid)){const id=String(n.node_id),inst=String((n as any).instance_epoch??'legacy');const prior=m.instanceByNode[id];",
    "for(const n of freshNodes(nodes,sid)){const id=String(n.node_id),inst=String((n as any).instance_epoch??'').trim();if(!inst||inst==='legacy')continue;const prior=m.instanceByNode[id];",
)
# logical_membership_state is observability, not an authority-bearing control. Keep only a
# compact cohort hint on the wire; the full membership/transition state stays in JSON diagnostics.
replace_once(
    "apps/mobile/src/humanPresence.ts",
    "logical_membership_state:{expected_cohort:stableCohort(nodes),transport_liveness_state:transportStates(nodes)}",
    "logical_membership_state:{schema:'LogicalMembershipWireV2',c:stableCohort(nodes)}",
)

# Pre-run evidence identity.
replace_once(
    "apps/mobile/App.tsx",
    "release:'dev-20.13',build:BUILD,evidence_schema:'v16'",
    "release:'dev-20.14',build:BUILD,evidence_schema:'v17'",
)
replace_once(
    "apps/mobile/App.tsx",
    "pre-run-diagnostic-dev20.13-",
    "pre-run-diagnostic-dev20.14-",
)

# Coherent release metadata.
write("apps/mobile/src/version.ts", """export const RELEASE = Object.freeze({\n  build: '0.2.0-experimental.20.14',\n  reportVersion: 34,\n  versionCode: 34,\n  releaseIteration: 'experimental.20.14',\n  protocolVersion: 2,\n  snapshotSchemaVersion: 16,\n  acceptanceMinimumMs: 330000,\n  humanScanningEnabled: true,\n  humanLocalizationValidated: false,\n  rescueUseValidated: false,\n});\nexport const BUILD = RELEASE.build;\nexport const REPORT_VERSION = RELEASE.reportVersion;\nexport const HUMAN_SCANNING_ENABLED = RELEASE.humanScanningEnabled;\n""")

app_json_path = ROOT / "apps/mobile/app.json"
app = json.loads(app_json_path.read_text(encoding="utf-8"))
app["expo"]["version"] = "0.2.0-experimental.20.14"
app["expo"]["android"]["versionCode"] = 34
app["expo"]["extra"]["releaseIteration"] = "experimental.20.14"
app["version"] = "0.2.0-experimental.20.14"
app.setdefault("android", {})["versionCode"] = 34
app_json_path.write_text(json.dumps(app, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

legacy_path = "apps/android-legacy/app/build.gradle"
legacy = read(legacy_path).replace("versionCode 33", "versionCode 34").replace("0.2.0-experimental.20.13-legacy", "0.2.0-experimental.20.14-legacy")
write(legacy_path, legacy)

package_path = ROOT / "apps/mobile/package.json"
package = json.loads(package_path.read_text(encoding="utf-8")); package["version"] = "0.2.0-experimental.20.14"
package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
lock_path = ROOT / "apps/mobile/package-lock.json"
lock = json.loads(lock_path.read_text(encoding="utf-8")); lock["version"] = "0.2.0-experimental.20.14"; lock["packages"][""]["version"] = "0.2.0-experimental.20.14"
lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

write("validation/schemas/authority-wire-v2-schema.json", json.dumps({
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "authority-wire-v2-schema.json",
    "title": "AuthorityWireV2",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "s", "e", "g", "b", "d"],
    "properties": {
        "schema": {"const": "AuthorityWireV2"},
        "s": {"type": "string", "minLength": 1},
        "e": {"type": "string", "minLength": 1},
        "g": {"type": "integer", "minimum": 1},
        "b": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "d": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    }
}, indent=2) + "\n")
write("validation/schemas/authority-ack-wire-v2-schema.json", json.dumps({
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "authority-ack-wire-v2-schema.json",
    "title": "AuthorityAckWireV2",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "s", "n", "e", "g", "b", "d"],
    "properties": {
        "schema": {"const": "AuthorityAckWireV2"},
        "s": {"type": "string", "minLength": 1},
        "n": {"type": "string", "minLength": 1},
        "e": {"type": "string", "minLength": 1},
        "g": {"type": "integer", "minimum": 1},
        "b": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "d": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    }
}, indent=2) + "\n")

print("dev20.14 remediation applied")
