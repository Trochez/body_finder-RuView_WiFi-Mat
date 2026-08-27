import { Advertisement } from './autogeometry';

export type HumanPresenceState = 'HUMAN_EVIDENCE' | 'NO_HUMAN_EVIDENCE' | 'INDETERMINATE';
export type HumanPresencePreview = { prediction: HumanPresenceState; human_confidence: number; evidence_quality: 'LOW'|'MEDIUM'|'HIGH'; aggregate_change_score: number; contributing_nodes: number; reason: string; algorithm_version: 'connected-wifi-rssi-preview-v1' };
const sigmoid=(x:number)=>1/(1+Math.exp(-Math.max(-40,Math.min(40,x))));

/** Conservative live presence-only preview. Physical acceptance uses exported raw BLE evidence, not this UI value. */
export function estimateHumanPresence(nodes: Advertisement[]): HumanPresencePreview {
  const values=nodes.flatMap(node=>{
    if(!node.scanning || node.rssi_dbm==null || node.baseline_rssi_dbm==null) return [];
    const sigma=Math.max(1,node.baseline_sigma_db??2); return [{score:Math.min(25,Math.abs(node.rssi_dbm-node.baseline_rssi_dbm)/sigma),quality:sigma<=8?1:0.6}];
  });
  if(values.length<2) return {prediction:'INDETERMINATE',human_confidence:0,evidence_quality:'LOW',aggregate_change_score:0,contributing_nodes:values.length,reason:'insufficient independent calibrated nodes',algorithm_version:'connected-wifi-rssi-preview-v1'};
  const w=values.reduce((s,v)=>s+v.quality,0); const score=values.reduce((s,v)=>s+v.score*v.quality,0)/Math.max(.01,w); const p=Math.max(.05,Math.min(.95,.05+.9*sigmoid((score-1.25)*2.2))); const q=values.length>=3?'HIGH':'MEDIUM';
  if(score>=1.65) return {prediction:'HUMAN_EVIDENCE',human_confidence:p,evidence_quality:q,aggregate_change_score:score,contributing_nodes:values.length,reason:'calibrated multi-node RF disturbance exceeds deterministic threshold',algorithm_version:'connected-wifi-rssi-preview-v1'};
  if(score<=.85) return {prediction:'NO_HUMAN_EVIDENCE',human_confidence:1-p,evidence_quality:q,aggregate_change_score:score,contributing_nodes:values.length,reason:'compatible with calibrated background; not proof of absence',algorithm_version:'connected-wifi-rssi-preview-v1'};
  return {prediction:'INDETERMINATE',human_confidence:Math.max(p,1-p),evidence_quality:q,aggregate_change_score:score,contributing_nodes:values.length,reason:'inside conservative decision band',algorithm_version:'connected-wifi-rssi-preview-v1'};
}
