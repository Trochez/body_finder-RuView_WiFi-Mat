import type { Advertisement } from './autogeometry';
import { DETECTOR, DETECTOR_ALGORITHM, DETECTOR_PARAMETER_HASH } from './detectorParameters';

export type HumanPresencePreview = {
  prediction:'HUMAN_EVIDENCE'|'NO_HUMAN_EVIDENCE'|'INDETERMINATE'; confidence:number; human_confidence:number; quality:number; evidence_quality:'HIGH'|'MEDIUM'|'LOW';
  aggregate_normalized_change:number|null; fused_score:number|null; contributing_nodes:number; contributing_links:number;
  physical_baselines:number; reciprocal_coherence:number|null; disturbed_links:number; disturbed_baselines:number;
  components:Record<string,number>; reason:string; calibration_state:string; algorithm_version:string; parameter_hash:string;
  decision_id:string; window_id:string; authoritative:boolean; source:'coordinator'|'coordinator-publication'|'diagnostic';
};
type S={observer:string,peer:string,median:number,quality:number,wall:number};
const clamp=(x:number)=>Math.max(0,Math.min(DETECTOR.featureClip,x));
const median=(xs:number[])=>{const a=[...xs].sort((x,y)=>x-y);return a.length? (a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2):0};
const mean=(xs:number[])=>xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:0;
const variance=(xs:number[])=>{const m=mean(xs);return xs.length?mean(xs.map(x=>(x-m)**2)):0};
const iqr=(xs:number[])=>{if(!xs.length)return 0;const a=[...xs].sort((x,y)=>x-y);const q=(t:number)=>a[Math.min(a.length-1,Math.floor((a.length-1)*t))];return q(.75)-q(.25)};
const hash=(s:string)=>{let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return ('00000000'+(h>>>0).toString(16)).slice(-8)};
type LinkHistory={baseline:number,sigma:number,values:number[],wall:number[],quality:number,observer:string,peer:string};
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
}
export function estimateHumanPresence(nodes:Advertisement[], source:'coordinator'|'diagnostic'='diagnostic'):HumanPresencePreview{
 const m=sampleMap(nodes), links=[...m.entries()].filter(([,x])=>x.values.length>=3);const observers=new Set(links.map(([,x])=>x.observer));const baselines=new Set(links.map(([,x])=>[x.observer,x.peer].sort().join('::')));
 const window=`${Math.floor(Date.now()/2000)*2000}`; const base={confidence:0,human_confidence:0,quality:0,evidence_quality:'LOW' as const,aggregate_normalized_change:null,fused_score:null,contributing_nodes:observers.size,contributing_links:links.length,physical_baselines:baselines.size,reciprocal_coherence:null,disturbed_links:0,disturbed_baselines:0,components:{},calibration_state:'SESSION_EMPTY_CAL_REQUIRED',algorithm_version:DETECTOR_ALGORITHM,parameter_hash:DETECTOR_PARAMETER_HASH,window_id:window,decision_id:'',authoritative:source==='coordinator',source} as HumanPresencePreview;
 const finish=(prediction:HumanPresencePreview['prediction'],reason:string,score:number|null,extra:Partial<HumanPresencePreview>={})=>{const seed=`${window}|${DETECTOR_ALGORITHM}|${DETECTOR_PARAMETER_HASH}|${prediction}|${score??'null'}|${[...m.keys()].sort().join(',')}`;const confidence=typeof (extra as any).confidence==='number'?(extra as any).confidence:(prediction==='INDETERMINATE'?0:Math.max(0,Math.min(1,score??0))); const quality=typeof (extra as any).quality==='number'?(extra as any).quality:base.quality; const evidence_quality:HumanPresencePreview['evidence_quality']=quality>=.75?'HIGH':quality>=.45?'MEDIUM':'LOW'; return {...base,...extra,prediction,reason,fused_score:score,confidence,human_confidence:confidence,quality,evidence_quality,decision_id:`d203-${hash(seed)}`}};
 if(observers.size<DETECTOR.minObserverNodes||links.length<DETECTOR.minDirectionalLinks||baselines.size<DETECTOR.minPhysicalBaselines)return finish('INDETERMINATE','full_3node_6link_3baseline_topology_required',null);
 const feats=links.map(([k,x])=>{const v=x.values,b=x.baseline,s=x.sigma,abs=mean(v.map(z=>Math.abs(z-b)))/s,med=Math.abs(median(v)-b)/s,mn=Math.abs(mean(v)-b)/s,vr=variance(v)/(s*s),iq=iqr(v)/(1.349*s),der=v.length>1?mean(v.slice(1).map((z,i)=>Math.abs(z-v[i])))/s:0,occ=mean(v.map(z=>Math.abs(z-b)>=Math.max(3,2.5*s)?1:0));let best=0,cur=0;for(const z of v){cur=Math.abs(z-b)>=Math.max(3,2.5*s)?cur+1:0;best=Math.max(best,cur)}const pers=best/Math.max(1,v.length);const mad=median(v.map(z=>Math.abs(z-median(v))))/(.6745*s);const slope=der;const w=DETECTOR.weights;const score=clamp(w.medianShift*med+w.meanShift*mn+w.madChange*mad+w.varianceChange*vr+w.iqrChange*iq+w.derivativeEnergy*der+w.slopeActivity*slope+w.deviationOccupancy*occ*4+w.persistence*pers*4);return {k,x,score,disturbed:score>=.48||occ>=.22||der>=.85,abs}});
 const q=mean(feats.map(f=>f.x.quality));if(q<DETECTOR.minMeanQuality)return finish('INDETERMINATE','mean_quality_below_gate',null,{quality:q});
 const reciprocal=mean(feats.map(f=>{const r=feats.find(g=>g.x.observer===f.x.peer&&g.x.peer===f.x.observer);return r?Math.max(0,1-Math.abs(f.score-r.score)/DETECTOR.featureClip):0}));const disturbed=feats.filter(f=>f.disturbed),db=new Set(disturbed.map(f=>[f.x.observer,f.x.peer].sort().join('::')));const baseScore=mean(feats.map(f=>f.score));const cross=disturbed.length/feats.length;const fs=clamp(baseScore+DETECTOR.fusion.reciprocalSupport*reciprocal+DETECTOR.fusion.crossLinkSupport*cross+DETECTOR.fusion.observerSupport*Math.min(1,observers.size/3)+DETECTOR.fusion.baselineSupport*Math.min(1,baselines.size/3));const extra={quality:q,aggregate_normalized_change:mean(feats.map(f=>f.abs)),reciprocal_coherence:reciprocal,disturbed_links:disturbed.length,disturbed_baselines:db.size,components:{base_score:baseScore,reciprocal,cross_link_support:cross,observer_support:observers.size/3,baseline_support:baselines.size/3}};
 if(fs>=DETECTOR.humanSupportScore&&disturbed.length>=DETECTOR.humanMinDisturbedLinks&&db.size>=DETECTOR.humanMinDisturbedBaselines)return finish('HUMAN_EVIDENCE','multi_feature_multi_link_disturbance',fs,extra);
 if(fs<=DETECTOR.noHumanMaxScore&&disturbed.length<=DETECTOR.noHumanMaxDisturbedLinks)return finish('NO_HUMAN_EVIDENCE','affirmative_clean_background_evidence',fs,extra);
 return finish('INDETERMINATE','ambiguous_disturbance',fs,extra);
}
export function selectAuthoritativePresence(nodes:Advertisement[], coordinatorId:string|null, localNodeId:string|null, localDiagnostic:HumanPresencePreview):HumanPresencePreview{
 if(!coordinatorId)return {...localDiagnostic,prediction:'INDETERMINATE',reason:'no_coordinator',authoritative:false,source:'diagnostic'};
 if(coordinatorId===localNodeId)return {...localDiagnostic,authoritative:true,source:'coordinator'};
 const coordinator=nodes.find(n=>n.node_id===coordinatorId) as any;const publication=coordinator?.published_geometry?.authoritative_presence;
 if(publication&&publication.algorithm_version===DETECTOR_ALGORITHM&&publication.parameter_hash===DETECTOR_PARAMETER_HASH&&publication.authoritative===true)return {...publication,source:'coordinator-publication'} as HumanPresencePreview;
 return {...localDiagnostic,prediction:'INDETERMINATE',confidence:0,reason:'waiting_for_coordinator_authoritative_publication',authoritative:false,source:'diagnostic'};
}
