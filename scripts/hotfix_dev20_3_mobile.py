#!/usr/bin/env python3
import pathlib
R=pathlib.Path(__file__).resolve().parents[1]
p=R/'apps/mobile/src/humanPresence.ts'; s=p.read_text()
# Preserve UI/export compatibility aliases while the v3 contract carries richer fields.
s=s.replace("prediction:'HUMAN_EVIDENCE'|'NO_HUMAN_EVIDENCE'|'INDETERMINATE'; confidence:number; quality:number;",
            "prediction:'HUMAN_EVIDENCE'|'NO_HUMAN_EVIDENCE'|'INDETERMINATE'; confidence:number; human_confidence:number; quality:number; evidence_quality:'HIGH'|'MEDIUM'|'LOW';")
old="""function sampleMap(nodes:Advertisement[]){const m=new Map<string,{baseline:number,sigma:number,values:number[],wall:number[],quality:number,observer:string,peer:string}>();for(const n of nodes){for(const r of n.ranges??[]){if(typeof r.rssi_dbm!=='number'||!r.peer_node_id)continue;const peer=String(r.peer_node_id),k=`${n.node_id}::${peer}`,x=m.get(k)??{baseline:typeof n.baseline_rssi_dbm==='number'?n.baseline_rssi_dbm:r.rssi_dbm,sigma:Math.max(1,typeof n.baseline_sigma_db==='number'?n.baseline_sigma_db:2),values:[],wall:[],quality:0,observer:n.node_id,peer};x.values.push(r.rssi_dbm);x.wall.push(typeof r.source_observation_monotonic_ns==='number'?r.source_observation_monotonic_ns/1e6:Date.now());x.quality=Math.max(x.quality,typeof r.quality==='number'?r.quality:.5);m.set(k,x)}}return m}"""
new="""type LinkHistory={baseline:number,sigma:number,values:number[],wall:number[],quality:number,observer:string,peer:string};
const HISTORY_MS=120000;
const history=new Map<string,LinkHistory>();
function sampleMap(nodes:Advertisement[]){
 const now=Date.now();
 for(const n of nodes){for(const r of n.ranges??[]){
  if(typeof r.rssi_dbm!=='number'||!r.peer_node_id)continue;
  const peer=String(r.peer_node_id),k=`${n.node_id}::${peer}`;
  const nativeStamp=(r as any).source_observation_monotonic_ns;
  const stamp=typeof nativeStamp==='number'?nativeStamp/1e6:now;
  const x=history.get(k)??{baseline:typeof n.baseline_rssi_dbm==='number'?n.baseline_rssi_dbm:r.rssi_dbm,sigma:Math.max(1,typeof n.baseline_sigma_db==='number'?n.baseline_sigma_db:2),values:[],wall:[],quality:0,observer:n.node_id,peer};
  if(x.wall.at(-1)!==stamp){x.values.push(r.rssi_dbm);x.wall.push(stamp)}
  x.baseline=typeof n.baseline_rssi_dbm==='number'?n.baseline_rssi_dbm:x.baseline;
  x.sigma=Math.max(1,typeof n.baseline_sigma_db==='number'?n.baseline_sigma_db:x.sigma);
  x.quality=Math.max(x.quality,typeof r.quality==='number'?r.quality:.5);
  while(x.values.length>180){x.values.shift();x.wall.shift()}
  history.set(k,x);
 }}
 const active=new Set<string>();for(const n of nodes)for(const r of n.ranges??[])if(r.peer_node_id)active.add(`${n.node_id}::${String(r.peer_node_id)}`);
 for(const k of [...history.keys()])if(!active.has(k))history.delete(k);
 return new Map([...history.entries()].filter(([,x])=>x.wall.length&&now-(x.wall.at(-1)??now)<=HISTORY_MS));
}"""
if old not in s: raise SystemExit('generated mobile sampleMap pattern not found')
s=s.replace(old,new)
s=s.replace("const base={confidence:0,quality:0,aggregate_normalized_change:null,",
            "const base={confidence:0,human_confidence:0,quality:0,evidence_quality:'LOW' as const,aggregate_normalized_change:null,")
s=s.replace("return {...base,...extra,prediction,reason,fused_score:score,decision_id:`d203-${hash(seed)}`}",
            "const confidence=typeof (extra as any).confidence==='number'?(extra as any).confidence:(prediction==='INDETERMINATE'?0:Math.max(0,Math.min(1,score??0))); const quality=typeof (extra as any).quality==='number'?(extra as any).quality:base.quality; const evidence_quality:HumanPresencePreview['evidence_quality']=quality>=.75?'HIGH':quality>=.45?'MEDIUM':'LOW'; return {...base,...extra,prediction,reason,fused_score:score,confidence,human_confidence:confidence,quality,evidence_quality,decision_id:`d203-${hash(seed)}`}")
required=['human_confidence:number','evidence_quality:',"(r as any).source_observation_monotonic_ns",'HISTORY_MS=120000']
missing=[x for x in required if x not in s]
if missing: raise SystemExit('mobile compatibility hardening incomplete: '+repr(missing))
p.write_text(s)
print('DEV20_3_MOBILE_HISTORY_HARDENING_APPLIED')
