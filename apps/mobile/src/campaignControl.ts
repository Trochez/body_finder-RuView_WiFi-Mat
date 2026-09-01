import BodyFinderNative from '../modules/body-finder-native';
import { Advertisement } from './autogeometry';

export type ScenarioId = 'SMOKE_CAL_EMPTY'|'HUMAN_MOVING'|'EMPTY_CAL'|'EMPTY_TEST'|'HUMAN_STATIONARY_CENTER'|'HUMAN_NEAR_LENOVO'|'HUMAN_NEAR_PIXEL10'|'HUMAN_NEAR_PIXEL7'|'HUMAN_OUTSIDE'|'NON_HUMAN_MOTION';
export type ScenarioCommandV1 = {schema:'ScenarioCommandV1';campaign_id:string;run_ordinal:number;scenario:ScenarioId;scenario_generation:number;issued_by:string;issued_wall_ms:number;command_digest:string};
type Ready={schema:'SnapshotReadyV1';node_id:string;run_token:string;scenario_digest:string;calibration_id:string;calibration_hash:string;calibration_generation:number;decision_id:string;decision_digest:string;replay_hash:string};
type Prepare={schema:'RunFreezePrepareV1';run_token:string;scenario_digest:string;generation:number;issued_by:string;issued_wall_ms:number};
type Commit={schema:'RunFreezeCommitV1';run_token:string;scenario_digest:string;generation:number;readiness_digest:string;committed_by:string;committed_wall_ms:number};

let command:ScenarioCommandV1|null=null;
let commandGeneration=0;
let runOrdinal=0;
let prepare:Prepare|null=null;
let commit:Commit|null=null;

function canonical(v:any):string {
  if(v===null||typeof v!=='object')return JSON.stringify(v);
  if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';
  return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
}
function sha(v:unknown){return BodyFinderNative.sha256Text(typeof v==='string'?v:canonical(v));}
function cohort(nodes:Advertisement[]){return [...new Set(nodes.filter(n=>n.protocol_version===2&&n.node_id).map(n=>String(n.node_id)))].sort().slice(0,3);}
function coordinatorNode(nodes:Advertisement[],id:string|null){return id?nodes.find(n=>n.node_id===id):undefined;}

function syncCommand(nodes:Advertisement[],coordinatorId:string|null,localId:string|null){
  if(!coordinatorId||coordinatorId===localId)return;
  const remote=(coordinatorNode(nodes,coordinatorId)?.control_plane as any)?.scenario_command_v1 as ScenarioCommandV1|undefined;
  if(!remote||remote.schema!=='ScenarioCommandV1'||remote.issued_by!==coordinatorId||!remote.command_digest)return;
  const material={campaign_id:remote.campaign_id,run_ordinal:Number(remote.run_ordinal),scenario:remote.scenario,scenario_generation:Number(remote.scenario_generation),issued_by:remote.issued_by,issued_wall_ms:Number(remote.issued_wall_ms)};
  if(sha(material)!==remote.command_digest)return;
  if(!command||remote.scenario_generation>command.scenario_generation||(remote.scenario_generation===command.scenario_generation&&remote.command_digest!==command.command_digest)){
    command=remote;commandGeneration=Math.max(commandGeneration,remote.scenario_generation);runOrdinal=Math.max(runOrdinal,remote.run_ordinal);prepare=null;commit=null;
  }
}

export function issueScenarioCommand(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,scenario:ScenarioId){
  if(!localId||coordinatorId!==localId)throw new Error('SCENARIO_COMMAND_COORDINATOR_ONLY');
  const ids=cohort(nodes);if(ids.length!==3||!ids.includes(localId))throw new Error('SCENARIO_COMMAND_REQUIRES_3_NODE_COHORT');
  commandGeneration+=1;runOrdinal+=1;const issued_wall_ms=Date.now();const campaign_id=String(nodes.find(n=>n.node_id===localId)?.session_id||'body-finder-lab');
  const material={campaign_id,run_ordinal:runOrdinal,scenario,scenario_generation:commandGeneration,issued_by:localId,issued_wall_ms};
  command={schema:'ScenarioCommandV1',...material,command_digest:sha(material)};prepare=null;commit=null;return command;
}

export function getScenarioCommandStatus(nodes:Advertisement[],coordinatorId:string|null,localId:string|null){
  syncCommand(nodes,coordinatorId,localId);const ids=cohort(nodes);const c=command;
  const ackMatrix=ids.map(id=>{if(!c)return{node_id:id,acknowledged:false};if(id===localId)return{node_id:id,acknowledged:true,digest:c.command_digest};const n=nodes.find(x=>x.node_id===id);const a=(n?.control_plane as any)?.scenario_ack_v1;return{node_id:id,acknowledged:Boolean(a&&a.schema==='ScenarioAckV1'&&a.node_id===id&&a.command_digest===c.command_digest&&Number(a.scenario_generation)===c.scenario_generation),digest:a?.command_digest??null}});
  return{schema:'ScenarioStatusV1',command:c,ack_matrix:ackMatrix,ack_count:ackMatrix.filter(x=>x.acknowledged).length,ready:Boolean(c&&ids.length===3&&ackMatrix.every(x=>x.acknowledged))};
}

function localReady(commandDigest:string,localId:string|null,presence:any,calibration:any):Ready|null{
  if(!localId||!presence?.authoritative||!presence?.decision_id||!presence?.canonical_digest||!presence?.canonical_replay_input)return null;
  if(Number(presence?.contributing_nodes??0)<3||Number(presence?.contributing_links??0)<6||Number(presence?.physical_baselines??0)<3)return null;
  const cid=String(calibration?.calibration_id??presence?.calibration_id??''),ch=String(calibration?.calibration_hash??presence?.calibration_hash??'');if(!cid||!ch)return null;
  return{schema:'SnapshotReadyV1',node_id:localId,run_token:commandDigest,scenario_digest:commandDigest,calibration_id:cid,calibration_hash:ch,calibration_generation:Number(calibration?.generation??calibration?.calibration_generation??presence?.calibration_generation??0),decision_id:String(presence.decision_id),decision_digest:String(presence.canonical_digest),replay_hash:sha(presence.canonical_replay_input)};
}
function syncPrepareCommit(nodes:Advertisement[],coordinatorId:string|null,localId:string|null){
  if(!coordinatorId||coordinatorId===localId)return;const cp=coordinatorNode(nodes,coordinatorId)?.control_plane as any;
  const rp=cp?.run_freeze_prepare_v1 as Prepare|undefined;if(rp&&rp.schema==='RunFreezePrepareV1'&&command&&rp.run_token===command.command_digest&&(!prepare||rp.generation>=prepare.generation))prepare=rp;
  const rc=cp?.run_freeze_commit_v1 as Commit|undefined;if(rc&&rc.schema==='RunFreezeCommitV1'&&command&&rc.run_token===command.command_digest&&prepare&&rc.generation===prepare.generation)commit=rc;
}
export function requestRunFreeze(nodes:Advertisement[],coordinatorId:string|null,localId:string|null){
  syncCommand(nodes,coordinatorId,localId);if(!localId||coordinatorId!==localId)throw new Error('RUN_FREEZE_COORDINATOR_ONLY');if(!command)throw new Error('RUN_FREEZE_SCENARIO_MISSING');
  prepare={schema:'RunFreezePrepareV1',run_token:command.command_digest,scenario_digest:command.command_digest,generation:(prepare?.generation??0)+1,issued_by:localId,issued_wall_ms:Date.now()};commit=null;return prepare;
}
export function getFreezeBarrierStatus(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,presence:any,calibration:any){
  syncCommand(nodes,coordinatorId,localId);syncPrepareCommit(nodes,coordinatorId,localId);const ids=cohort(nodes);const local=prepare&&command?localReady(command.command_digest,localId,presence,calibration):null;
  const ready:Ready[]=[];for(const id of ids){if(id===localId&&local)ready.push(local);else{const a=(nodes.find(n=>n.node_id===id)?.control_plane as any)?.snapshot_ready_v1 as Ready|undefined;if(a&&a.schema==='SnapshotReadyV1'&&prepare&&a.run_token===prepare.run_token&&a.scenario_digest===prepare.scenario_digest)ready.push(a)}}
  const signatures=ready.map(r=>canonical({run_token:r.run_token,scenario_digest:r.scenario_digest,calibration_id:r.calibration_id,calibration_hash:r.calibration_hash,calibration_generation:r.calibration_generation,decision_id:r.decision_id,decision_digest:r.decision_digest,replay_hash:r.replay_hash}));const parity=ready.length===3&&new Set(signatures).size===1;
  if(coordinatorId===localId&&prepare&&parity&&!commit){const readiness_digest=sha(ready.slice().sort((a,b)=>a.node_id.localeCompare(b.node_id)));commit={schema:'RunFreezeCommitV1',run_token:prepare.run_token,scenario_digest:prepare.scenario_digest,generation:prepare.generation,readiness_digest,committed_by:localId!,committed_wall_ms:Date.now()};}
  return{schema:'SnapshotFreezeV1',prepare,local_ready:local,ready_count:ready.length,ready_nodes:ready.map(r=>r.node_id).sort(),ready_parity:parity,commit,committed:Boolean(commit&&prepare&&commit.run_token===prepare.run_token&&commit.generation===prepare.generation)};
}
export function getCampaignControlPublication(nodes:Advertisement[],coordinatorId:string|null,localId:string|null,presence:any,calibration:any){
  const s=getScenarioCommandStatus(nodes,coordinatorId,localId);const f=getFreezeBarrierStatus(nodes,coordinatorId,localId,presence,calibration);const c=s.command;
  return{scenario_command_v1:coordinatorId===localId?c:null,scenario_ack_v1:c&&localId?{schema:'ScenarioAckV1',node_id:localId,scenario_generation:c.scenario_generation,command_digest:c.command_digest}:null,run_freeze_prepare_v1:coordinatorId===localId?f.prepare:null,snapshot_ready_v1:f.local_ready,run_freeze_commit_v1:coordinatorId===localId?f.commit:null};
}
