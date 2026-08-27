import { Advertisement } from './autogeometry';

export type HumanPresenceState = 'HUMAN_EVIDENCE' | 'NO_HUMAN_EVIDENCE' | 'INDETERMINATE';
export type HumanPresencePreview = {
  prediction: HumanPresenceState; human_confidence: number; evidence_quality: 'LOW'|'MEDIUM'|'HIGH';
  aggregate_change_score: number; contributing_nodes: number; contributing_links: number; physical_baselines: number;
  reciprocal_pair_count: number; simultaneous_disturbed_links: number; component_scores: Record<string,number>;
  reason: string; calibration_state: 'WAITING_FOR_EMPTY_CAL'|'CALIBRATED'; algorithm_version: 'deterministic-multinode-rssi-fusion-v2-online';
};

type Sample={t:number;r:number}; type Baseline={values:number[]};
const history=new Map<string,Sample[]>(); const baseline=new Map<string,Baseline>(); let calibrationSignature='';
const median=(v:number[])=>{const s=[...v].sort((a,b)=>a-b),m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2};
const mean=(v:number[])=>v.length?v.reduce((a,b)=>a+b,0)/v.length:0;
const variance=(v:number[])=>{const m=mean(v);return v.length?mean(v.map(x=>(x-m)**2)):0};
const mad=(v:number[])=>{if(!v.length)return 0;const m=median(v);return median(v.map(x=>Math.abs(x-m)))};
const diffEnergy=(v:number[])=>v.length>1?mean(v.slice(1).map((x,i)=>(x-v[i])**2)):0;
const clip=(x:number)=>Math.max(0,Math.min(4,x)); const sigmoid=(x:number)=>1/(1+Math.exp(-Math.max(-40,Math.min(40,x))));
const physical=(lid:string)=>lid.split('::').slice(0,2).sort().join('::');

function ingest(nodes:Advertisement[],now:number){
  const seen=new Set<string>();
  for(const n of nodes) for(const r of n.ranges??[]){
    if(r.technology!=='BLE_RSSI'||r.rssi_dbm==null||(r as any).range_temporal_state==='HOLDOVER') continue;
    const observer=r.observer_node_id||n.node_id, peer=r.peer_node_id; if(!observer||!peer) continue;
    const lid=`${observer}::${peer}`; seen.add(lid); const q=history.get(lid)??[]; q.push({t:now,r:Number(r.rssi_dbm)});
    while(q.length&&now-q[0].t>30_000) q.shift(); if(q.length>120) q.splice(0,q.length-120); history.set(lid,q);
  }
  for(const [lid,q] of history) if(!seen.has(lid)) while(q.length&&now-q[0].t>30_000) q.shift();
}
function maybeFreezeCalibration(nodes:Advertisement[]){
  const calibrated=nodes.filter(n=>n.baseline_rssi_dbm!=null&&n.baseline_sigma_db!=null).map(n=>`${n.node_id}:${Number(n.baseline_rssi_dbm).toFixed(2)}:${Number(n.baseline_sigma_db).toFixed(2)}`).sort();
  if(calibrated.length<2)return; const sig=calibrated.join('|'); if(sig===calibrationSignature)return;
  const candidate=new Map<string,Baseline>(); for(const [lid,q] of history){const vals=q.map(x=>x.r);if(vals.length>=8)candidate.set(lid,{values:[...vals]});}
  if(candidate.size>=2){baseline.clear();for(const [k,v] of candidate)baseline.set(k,v);calibrationSignature=sig;}
}
/** Multi-node preview using the six BLE directional links already transported by the fabric. */
export function estimateHumanPresence(nodes: Advertisement[]): HumanPresencePreview {
  const now=Date.now(); ingest(nodes,now); maybeFreezeCalibration(nodes);
  const blank=(reason:string):HumanPresencePreview=>({prediction:'INDETERMINATE',human_confidence:0,evidence_quality:'LOW',aggregate_change_score:0,contributing_nodes:0,contributing_links:0,physical_baselines:0,reciprocal_pair_count:0,simultaneous_disturbed_links:0,component_scores:{},reason,calibration_state:baseline.size?'CALIBRATED':'WAITING_FOR_EMPTY_CAL',algorithm_version:'deterministic-multinode-rssi-fusion-v2-online'});
  if(!baseline.size)return blank('waiting for synchronized BLE empty-scene calibration from at least two nodes');
  const feats:{lid:string;score:number;q:number}[]=[];
  for(const [lid,b] of baseline){const o=(history.get(lid)??[]).filter(x=>now-x.t<=20_000).map(x=>x.r);if(b.values.length<8||o.length<8)continue;
    const bm=median(b.values),om=median(o),bs=Math.max(1,1.4826*mad(b.values),Math.sqrt(variance(b.values)));const bv=Math.max(.25,variance(b.values)),ov=variance(o);const bde=Math.max(.25,diffEnergy(b.values)),ode=diffEnergy(o);const band=Math.max(3,2.5*bs);const bo=mean(b.values.map(x=>Math.abs(x-bm)>=band?1:0)),oo=mean(o.map(x=>Math.abs(x-bm)>=band?1:0));
    const med=clip(Math.abs(om-bm)/bs),vr=clip(Math.log1p(Math.abs(ov-bv)/bv)),de=clip(Math.log1p(Math.abs(ode-bde)/bde)),occ=clip(Math.max(0,oo-bo)*4);const score=.24*med+.26*vr+.30*de+.20*occ;const q=Math.min(1,Math.min(b.values.length,o.length)/25);feats.push({lid,score,q});
  }
  const observers=new Set(feats.map(f=>f.lid.split('::')[0])),phys=new Set(feats.map(f=>physical(f.lid)));if(observers.size<2||phys.size<2)return blank('insufficient synchronized independent BLE topology; fail-closed');
  const total=feats.reduce((s,f)=>s+Math.max(.05,f.q),0),base=feats.reduce((s,f)=>s+f.score*Math.max(.05,f.q),0)/Math.max(.01,total);const byPhys=new Map<string,typeof feats>();for(const f of feats){const k=physical(f.lid),a=byPhys.get(k)??[];a.push(f);byPhys.set(k,a)}
  const reciprocal=[...byPhys.values()].filter(x=>x.length>=2),coherence=reciprocal.length?mean(reciprocal.map(v=>Math.max(0,1-Math.abs(v[0].score-v[1].score)/Math.max(.5,Math.max(v[0].score,v[1].score))))):0,disturbed=feats.filter(f=>f.score>=.9).length,cross=Math.min(1,disturbed/Math.max(2,feats.length)),fused=base*(.78+.12*coherence+.10*cross),mq=mean(feats.map(f=>f.q)),p=Math.max(.02,Math.min(.98,sigmoid((fused-.72)*4))),eq:HumanPresencePreview['evidence_quality']=mq>=.75&&observers.size>=3&&phys.size>=3?'HIGH':'MEDIUM';
  const common={aggregate_change_score:fused,contributing_nodes:observers.size,contributing_links:feats.length,physical_baselines:phys.size,reciprocal_pair_count:reciprocal.length,simultaneous_disturbed_links:disturbed,component_scores:{quality_weighted_link_score:base,reciprocal_coherence:coherence,cross_link_support:cross,mean_link_quality:mq},calibration_state:'CALIBRATED' as const,algorithm_version:'deterministic-multinode-rssi-fusion-v2-online' as const};
  if(fused>=1.05)return {...common,prediction:'HUMAN_EVIDENCE',human_confidence:p,evidence_quality:eq,reason:'multi-node temporal/variance BLE disturbance exceeds fused threshold'};
  if(fused<=.42)return {...common,prediction:'NO_HUMAN_EVIDENCE',human_confidence:1-p,evidence_quality:eq,reason:'multi-node evidence compatible with calibrated background; not proof of absence'};
  return {...common,prediction:'INDETERMINATE',human_confidence:Math.max(p,1-p),evidence_quality:eq,reason:'fused disturbance inside conservative decision band'};
}
