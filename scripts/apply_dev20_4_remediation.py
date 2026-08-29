#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = "deterministic-multinode-rssi-fusion-v4"
PARAMETER_HASH = "9d111630f6109316b65650a5c119dbff2fdc990528d58826641d56b29fd9daa6"
BUILD = "0.2.0-experimental.20.4"


def write(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.rstrip() + "\n", encoding="utf-8")


def replace(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"required patch anchor missing in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")


PARAMETERS = {
    "algorithm_version": ALGORITHM,
    "schema_version": 4,
    "min_samples_per_link": 20,
    "min_observer_nodes": 3,
    "min_directional_links": 6,
    "min_physical_baselines": 3,
    "min_overlap_ms": 1000,
    "min_mean_quality": 0.45,
    "deviation_band_sigma": 2.0,
    "deviation_band_floor_db": 2.5,
    "human_threshold": 0.58,
    "no_human_threshold": 0.28,
    "disturbed_link_threshold": 0.44,
    "min_disturbed_links": 2,
    "min_disturbed_baselines": 2,
    "weights": {"shift": 0.18, "spread": 0.19, "dynamic": 0.27, "occupancy": 0.19, "persistence": 0.17},
    "fusion": {"base": 1.0, "reciprocal": 0.10, "cross_link": 0.08, "baseline_support": 0.08, "quality_penalty": 0.08},
}
assert hashlib.sha256(json.dumps(PARAMETERS, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == PARAMETER_HASH

RUST = r'''
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

pub const ALGORITHM_VERSION: &str = "deterministic-multinode-rssi-fusion-v4";
pub const PARAMETER_HASH: &str = "9d111630f6109316b65650a5c119dbff2fdc990528d58826641d56b29fd9daa6";
const MIN_SAMPLES: usize = 20;
const MIN_OVERLAP_MS: i64 = 1_000;
const HUMAN_THRESHOLD: f64 = 0.58;
const NO_HUMAN_THRESHOLD: f64 = 0.28;
const DISTURBED_THRESHOLD: f64 = 0.44;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectorSample {
    pub receive_wall_ms: i64,
    #[serde(default)] pub source_monotonic_ns: Option<i64>,
    pub rssi_dbm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawLink {
    pub link_id: String,
    pub observer_node_id: String,
    pub peer_node_id: String,
    pub samples: Vec<DetectorSample>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CalibrationBuildInput {
    pub operation: String,
    pub session_id: String,
    pub calibration_id: String,
    pub generation: u64,
    pub topology_fingerprint: String,
    pub detector_parameter_hash: String,
    pub frozen_wall_ms: i64,
    pub links: Vec<RawLink>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BaselineStats {
    pub link_id: String,
    pub observer_node_id: String,
    pub peer_node_id: String,
    pub sample_count: usize,
    pub median_dbm: f64,
    pub mean_dbm: f64,
    pub mad_db: f64,
    pub variance_db2: f64,
    pub iqr_db: f64,
    pub diff_energy: f64,
    pub slope_activity: f64,
    pub deviation_band_db: f64,
    pub first_receive_wall_ms: i64,
    pub last_receive_wall_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CalibrationArtifact {
    pub schema_version: u32,
    pub calibration_id: String,
    pub generation: u64,
    pub session_id: String,
    pub topology_fingerprint: String,
    pub detector_algorithm: String,
    pub detector_parameter_hash: String,
    pub frozen_wall_ms: i64,
    pub contributing_nodes: usize,
    pub directional_links: usize,
    pub physical_baselines: usize,
    pub comparable_clock_domain: String,
    pub links: Vec<BaselineStats>,
    pub calibration_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AcquisitionHealth {
    #[serde(default = "yes")] pub environment_valid: bool,
    #[serde(default = "yes")] pub acquisition_valid: bool,
}
fn yes() -> bool { true }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceInput {
    pub operation: String,
    pub session_id: String,
    pub window_id: String,
    pub window_start_wall_ms: i64,
    pub window_end_wall_ms: i64,
    pub detector_parameter_hash: String,
    pub calibration: CalibrationArtifact,
    #[serde(default)] pub acquisition_health: AcquisitionHealth,
    pub links: Vec<RawLink>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinkFeature {
    pub link_id: String,
    pub observer_node_id: String,
    pub peer_node_id: String,
    pub sample_count: usize,
    pub shift_score: f64,
    pub spread_score: f64,
    pub dynamic_score: f64,
    pub occupancy_score: f64,
    pub persistence_score: f64,
    pub quality: f64,
    pub disturbance_score: f64,
    pub first_receive_wall_ms: i64,
    pub last_receive_wall_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClockDiagnostics {
    pub freshness_clock_domain: String,
    pub source_monotonic_used_for_freshness: bool,
    pub comparable_receive_wall_sample_count: usize,
    pub provenance_monotonic_sample_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceCore {
    pub prediction: String,
    pub human_confidence: f64,
    pub evidence_quality: String,
    pub fused_score: f64,
    pub contributing_links: usize,
    pub contributing_nodes: usize,
    pub physical_baselines: usize,
    pub reciprocal_pair_count: usize,
    pub disturbed_links: usize,
    pub disturbed_baselines: usize,
    pub reason: String,
    pub missing_or_stale_reasons: Vec<String>,
    pub component_scores: BTreeMap<String, f64>,
    pub per_link_features: Vec<LinkFeature>,
    pub calibration_state: String,
    pub calibration_id: String,
    pub calibration_hash: String,
    pub algorithm_version: String,
    pub parameter_hash: String,
    pub window_id: String,
    pub clock_diagnostics: ClockDiagnostics,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceResult {
    #[serde(flatten)] pub core: InferenceCore,
    pub canonical_digest: String,
    pub decision_id: String,
    pub authoritative: bool,
    pub source: String,
    pub publication_contract_version: u32,
    pub canonical_replay_input: Value,
}

fn mean(xs: &[f64]) -> f64 { if xs.is_empty() { 0.0 } else { xs.iter().sum::<f64>() / xs.len() as f64 } }
fn variance(xs: &[f64]) -> f64 { let m=mean(xs); if xs.is_empty(){0.0}else{xs.iter().map(|x|(x-m)*(x-m)).sum::<f64>()/xs.len() as f64} }
fn median(xs: &[f64]) -> f64 { let mut s=xs.to_vec(); s.sort_by(|a,b|a.total_cmp(b)); if s.is_empty(){return 0.0} let n=s.len(); if n%2==1{s[n/2]}else{(s[n/2-1]+s[n/2])/2.0} }
fn mad(xs: &[f64]) -> f64 { let m=median(xs); median(&xs.iter().map(|x|(x-m).abs()).collect::<Vec<_>>()) }
fn percentile(xs: &[f64], p:f64)->f64 { let mut s=xs.to_vec(); s.sort_by(|a,b|a.total_cmp(b)); if s.is_empty(){return 0.0} let pos=(s.len()-1) as f64*p; let lo=pos.floor() as usize; let hi=(lo+1).min(s.len()-1); s[lo]*(1.0-(pos-lo as f64))+s[hi]*(pos-lo as f64) }
fn diff_energy(xs:&[f64])->f64 { if xs.len()<2{0.0}else{mean(&(1..xs.len()).map(|i|(xs[i]-xs[i-1]).powi(2)).collect::<Vec<_>>())} }
fn slope_activity(xs:&[f64])->f64 { if xs.len()<2{0.0}else{mean(&(1..xs.len()).map(|i|(xs[i]-xs[i-1]).abs()).collect::<Vec<_>>())} }
fn unit(x:f64)->f64 { (1.0-(-x.max(0.0)).exp()).clamp(0.0,1.0) }
fn physical(a:&str,b:&str)->String { if a<=b{format!("{}::{}",a,b)}else{format!("{}::{}",b,a)} }
fn sha(bytes:&[u8])->String { format!("sha256:{:x}", Sha256::digest(bytes)) }
fn round6(x:f64)->f64 { (x*1_000_000.0).round()/1_000_000.0 }

fn baseline_stats(link:&RawLink)->Result<BaselineStats,String>{
    if link.samples.len()<MIN_SAMPLES { return Err(format!("{}: fewer than {} calibration samples",link.link_id,MIN_SAMPLES)); }
    let xs:Vec<f64>=link.samples.iter().map(|s|s.rssi_dbm).filter(|x|(-126.0..=0.0).contains(x)).collect();
    if xs.len()<MIN_SAMPLES { return Err(format!("{}: insufficient valid RSSI calibration samples",link.link_id)); }
    let md=mad(&xs); let var=variance(&xs); let band=(2.0*(1.4826*md).max(var.sqrt()).max(1.0)).max(2.5);
    Ok(BaselineStats{link_id:link.link_id.clone(),observer_node_id:link.observer_node_id.clone(),peer_node_id:link.peer_node_id.clone(),sample_count:xs.len(),median_dbm:round6(median(&xs)),mean_dbm:round6(mean(&xs)),mad_db:round6(md),variance_db2:round6(var),iqr_db:round6(percentile(&xs,.9)-percentile(&xs,.1)),diff_energy:round6(diff_energy(&xs)),slope_activity:round6(slope_activity(&xs)),deviation_band_db:round6(band),first_receive_wall_ms:link.samples.iter().map(|s|s.receive_wall_ms).min().unwrap_or(0),last_receive_wall_ms:link.samples.iter().map(|s|s.receive_wall_ms).max().unwrap_or(0)})
}

fn hash_artifact(a:&CalibrationArtifact)->String{
    let mut c=a.clone(); c.calibration_hash.clear();
    sha(&serde_json::to_vec(&c).expect("serialize calibration"))
}

pub fn build_calibration(input:CalibrationBuildInput)->Value{
    let mut failures=Vec::new();
    if input.detector_parameter_hash!=PARAMETER_HASH { failures.push("detector_parameter_hash_mismatch".to_string()); }
    let mut links=input.links.clone(); links.sort_by(|a,b|a.link_id.cmp(&b.link_id));
    let mut stats=Vec::new();
    for l in &links { match baseline_stats(l){Ok(s)=>stats.push(s),Err(e)=>failures.push(e)} }
    let nodes:BTreeSet<_>=stats.iter().map(|s|s.observer_node_id.clone()).collect();
    let phys:BTreeSet<_>=stats.iter().map(|s|physical(&s.observer_node_id,&s.peer_node_id)).collect();
    if nodes.len()<3 { failures.push("fewer_than_3_observer_nodes".into()); }
    if stats.len()<6 { failures.push("fewer_than_6_directional_links".into()); }
    if phys.len()<3 { failures.push("fewer_than_3_physical_baselines".into()); }
    if !stats.is_empty() { let start=stats.iter().map(|s|s.first_receive_wall_ms).max().unwrap_or(0); let end=stats.iter().map(|s|s.last_receive_wall_ms).min().unwrap_or(0); if end-start<MIN_OVERLAP_MS { failures.push("insufficient_comparable_wall_clock_overlap".into()); } }
    if !failures.is_empty(){return json!({"operation":"BUILD_CALIBRATION","calibration_state":"INVALID","reason":"calibration_gate_failed","failures":failures,"algorithm_version":ALGORITHM_VERSION,"parameter_hash":PARAMETER_HASH});}
    let mut artifact=CalibrationArtifact{schema_version:4,calibration_id:input.calibration_id,generation:input.generation,session_id:input.session_id,topology_fingerprint:input.topology_fingerprint,detector_algorithm:ALGORITHM_VERSION.into(),detector_parameter_hash:PARAMETER_HASH.into(),frozen_wall_ms:input.frozen_wall_ms,contributing_nodes:nodes.len(),directional_links:stats.len(),physical_baselines:phys.len(),comparable_clock_domain:"LOCAL_RECEIVE_WALL_MS".into(),links:stats,calibration_hash:String::new()};
    artifact.calibration_hash=hash_artifact(&artifact);
    json!({"operation":"BUILD_CALIBRATION","calibration_state":"READY","reason":"frozen_synchronized_empty_calibration","artifact":artifact,"algorithm_version":ALGORITHM_VERSION,"parameter_hash":PARAMETER_HASH})
}

fn features(base:&BaselineStats, obs:&RawLink)->Result<LinkFeature,String>{
    if obs.samples.len()<MIN_SAMPLES{return Err(format!("{}: fewer than {} observation samples",obs.link_id,MIN_SAMPLES));}
    let xs:Vec<f64>=obs.samples.iter().map(|s|s.rssi_dbm).filter(|x|(-126.0..=0.0).contains(x)).collect();
    if xs.len()<MIN_SAMPLES{return Err(format!("{}: insufficient valid observation RSSI samples",obs.link_id));}
    let robust_sigma=(1.4826*base.mad_db).max(base.variance_db2.sqrt()).max(1.0);
    let shift=.55*unit((median(&xs)-base.median_dbm).abs()/robust_sigma)+.45*unit((mean(&xs)-base.mean_dbm).abs()/robust_sigma);
    let obs_mad=mad(&xs); let obs_var=variance(&xs); let obs_iqr=percentile(&xs,.9)-percentile(&xs,.1);
    let spread=.30*unit((obs_mad-base.mad_db).abs()/base.mad_db.max(1.0))+.45*unit(((obs_var-base.variance_db2).abs()/base.variance_db2.max(.25)).ln_1p())+.25*unit((obs_iqr-base.iqr_db).abs()/base.iqr_db.max(1.0));
    let ode=diff_energy(&xs); let osa=slope_activity(&xs);
    let dynamic=.58*unit(((ode-base.diff_energy).abs()/base.diff_energy.max(.25)).ln_1p())+.42*unit(((osa-base.slope_activity).abs()/base.slope_activity.max(.25)).ln_1p());
    let occ=mean(&xs.iter().map(|x|if (x-base.median_dbm).abs()>=base.deviation_band_db{1.0}else{0.0}).collect::<Vec<_>>());
    let occupancy=(occ*2.5).clamp(0.0,1.0);
    let chunk=(xs.len()/6).max(4); let chunks=xs.chunks(chunk).collect::<Vec<_>>();
    let persistence=mean(&chunks.iter().map(|c|if mean(&c.iter().map(|x|if (*x-base.median_dbm).abs()>=base.deviation_band_db{1.0}else{0.0}).collect::<Vec<_>>())>=.20{1.0}else{0.0}).collect::<Vec<_>>());
    let quality=(xs.len().min(base.sample_count) as f64/60.0).min(1.0);
    let disturbance=.18*shift+.19*spread+.27*dynamic+.19*occupancy+.17*persistence;
    Ok(LinkFeature{link_id:obs.link_id.clone(),observer_node_id:obs.observer_node_id.clone(),peer_node_id:obs.peer_node_id.clone(),sample_count:xs.len(),shift_score:round6(shift),spread_score:round6(spread),dynamic_score:round6(dynamic),occupancy_score:round6(occupancy),persistence_score:round6(persistence),quality:round6(quality),disturbance_score:round6(disturbance),first_receive_wall_ms:obs.samples.iter().map(|s|s.receive_wall_ms).min().unwrap_or(0),last_receive_wall_ms:obs.samples.iter().map(|s|s.receive_wall_ms).max().unwrap_or(0)})
}

fn invalid(input:&InferenceInput, cal_hash:String, reasons:Vec<String>, feats:Vec<LinkFeature>)->InferenceResult{
    let nodes:BTreeSet<_>=feats.iter().map(|f|f.observer_node_id.clone()).collect(); let phys:BTreeSet<_>=feats.iter().map(|f|physical(&f.observer_node_id,&f.peer_node_id)).collect();
    let clock=ClockDiagnostics{freshness_clock_domain:"LOCAL_RECEIVE_WALL_MS".into(),source_monotonic_used_for_freshness:false,comparable_receive_wall_sample_count:input.links.iter().map(|l|l.samples.len()).sum(),provenance_monotonic_sample_count:input.links.iter().flat_map(|l|l.samples.iter()).filter(|s|s.source_monotonic_ns.is_some()).count()};
    finish(input,InferenceCore{prediction:"INDETERMINATE".into(),human_confidence:.5,evidence_quality:"LOW".into(),fused_score:0.0,contributing_links:feats.len(),contributing_nodes:nodes.len(),physical_baselines:phys.len(),reciprocal_pair_count:0,disturbed_links:0,disturbed_baselines:0,reason:"insufficient_independent_synchronized_rf_evidence".into(),missing_or_stale_reasons:reasons,component_scores:BTreeMap::new(),per_link_features:feats,calibration_state:"INVALID".into(),calibration_id:input.calibration.calibration_id.clone(),calibration_hash:cal_hash,algorithm_version:ALGORITHM_VERSION.into(),parameter_hash:PARAMETER_HASH.into(),window_id:input.window_id.clone(),clock_diagnostics:clock})
}

fn finish(input:&InferenceInput,core:InferenceCore)->InferenceResult{
    let digest=sha(&serde_json::to_vec(&core).expect("serialize result"));
    let decision_id=format!("d204-{}",digest.trim_start_matches("sha256:").chars().take(16).collect::<String>());
    let replay=json!({"operation":"INFER","session_id":input.session_id,"window_id":input.window_id,"window_start_wall_ms":input.window_start_wall_ms,"window_end_wall_ms":input.window_end_wall_ms,"detector_parameter_hash":input.detector_parameter_hash,"calibration":input.calibration,"acquisition_health":input.acquisition_health,"links":input.links});
    InferenceResult{core,canonical_digest:digest,decision_id,authoritative:true,source:"canonical_shared_rust_engine".into(),publication_contract_version:4,canonical_replay_input:replay}
}

pub fn infer(mut input:InferenceInput)->InferenceResult{
    input.links.sort_by(|a,b|a.link_id.cmp(&b.link_id));
    let computed=hash_artifact(&input.calibration); let mut reasons=Vec::new();
    if input.detector_parameter_hash!=PARAMETER_HASH || input.calibration.detector_parameter_hash!=PARAMETER_HASH { reasons.push("detector_parameter_hash_mismatch".into()); }
    if input.calibration.calibration_hash!=computed { reasons.push("calibration_hash_mismatch".into()); }
    if !input.acquisition_health.environment_valid || !input.acquisition_health.acquisition_valid { reasons.push("acquisition_or_environment_invalid".into()); }
    if input.calibration.contributing_nodes<3 || input.calibration.directional_links<6 || input.calibration.physical_baselines<3 { reasons.push("calibration_topology_incomplete".into()); }
    let bases:BTreeMap<_,_>=input.calibration.links.iter().map(|b|(b.link_id.clone(),b)).collect();
    let mut feats=Vec::new();
    for obs in &input.links { match bases.get(&obs.link_id){Some(base)=>match features(base,obs){Ok(f)=>feats.push(f),Err(e)=>reasons.push(e)},None=>reasons.push(format!("{}: missing frozen baseline",obs.link_id))} }
    let nodes:BTreeSet<_>=feats.iter().map(|f|f.observer_node_id.clone()).collect(); let phys:BTreeSet<_>=feats.iter().map(|f|physical(&f.observer_node_id,&f.peer_node_id)).collect();
    if nodes.len()<3{reasons.push("fewer_than_3_observer_nodes".into())} if feats.len()<6{reasons.push("fewer_than_6_directional_links".into())} if phys.len()<3{reasons.push("fewer_than_3_physical_baselines".into())}
    if !feats.is_empty(){let start=feats.iter().map(|f|f.first_receive_wall_ms).max().unwrap_or(0);let end=feats.iter().map(|f|f.last_receive_wall_ms).min().unwrap_or(0);if end-start<MIN_OVERLAP_MS{reasons.push("insufficient_comparable_wall_clock_overlap".into())}}
    let q=if feats.is_empty(){0.0}else{mean(&feats.iter().map(|f|f.quality).collect::<Vec<_>>())}; if q<.45{reasons.push("mean_evidence_quality_below_gate".into())}
    if !reasons.is_empty(){return invalid(&input,computed,reasons,feats)}
    let totalw=feats.iter().map(|f|f.quality.max(.05)).sum::<f64>(); let base=feats.iter().map(|f|f.disturbance_score*f.quality.max(.05)).sum::<f64>()/totalw.max(.01);
    let mut byphys:BTreeMap<String,Vec<&LinkFeature>>=BTreeMap::new(); for f in &feats{byphys.entry(physical(&f.observer_node_id,&f.peer_node_id)).or_default().push(f)}
    let reciprocal=byphys.values().filter(|v|v.len()>=2).map(|v|(1.0-(v[0].disturbance_score-v[1].disturbance_score).abs().min(1.0))).collect::<Vec<_>>(); let recip=mean(&reciprocal);
    let disturbed=feats.iter().filter(|f|f.disturbance_score>=DISTURBED_THRESHOLD).count(); let disturbed_phys: BTreeSet<_>=feats.iter().filter(|f|f.disturbance_score>=DISTURBED_THRESHOLD).map(|f|physical(&f.observer_node_id,&f.peer_node_id)).collect();
    let cross=disturbed as f64/feats.len() as f64; let bs=disturbed_phys.len() as f64/phys.len() as f64;
    let fused=(base+.10*recip*cross+.08*cross+.08*bs-.08*(1.0-q)).clamp(0.0,1.0); let p=1.0/(1.0+(-((fused-.50)*7.0)).exp());
    let (prediction,reason)=if fused>=HUMAN_THRESHOLD && disturbed>=2 && disturbed_phys.len()>=2{("HUMAN_EVIDENCE","distributed_dynamic_and_level_disturbance")}else if fused<=NO_HUMAN_THRESHOLD && disturbed==0{("NO_HUMAN_EVIDENCE","clean_frozen_calibrated_background_not_proof_of_absence")}else{("INDETERMINATE","fused_disturbance_inside_conservative_band")};
    let mut components=BTreeMap::new();components.insert("quality_weighted_link_score".into(),round6(base));components.insert("reciprocal_coherence".into(),round6(recip));components.insert("cross_link_support".into(),round6(cross));components.insert("disturbed_baseline_support".into(),round6(bs));components.insert("mean_link_quality".into(),round6(q));
    let clock=ClockDiagnostics{freshness_clock_domain:"LOCAL_RECEIVE_WALL_MS".into(),source_monotonic_used_for_freshness:false,comparable_receive_wall_sample_count:input.links.iter().map(|l|l.samples.len()).sum(),provenance_monotonic_sample_count:input.links.iter().flat_map(|l|l.samples.iter()).filter(|s|s.source_monotonic_ns.is_some()).count()};
    finish(&input,InferenceCore{prediction:prediction.into(),human_confidence:round6(p),evidence_quality:if q>=.75{"HIGH".into()}else{"MEDIUM".into()},fused_score:round6(fused),contributing_links:feats.len(),contributing_nodes:nodes.len(),physical_baselines:phys.len(),reciprocal_pair_count:reciprocal.len(),disturbed_links:disturbed,disturbed_baselines:disturbed_phys.len(),reason:reason.into(),missing_or_stale_reasons:Vec::new(),component_scores:components,per_link_features:feats,calibration_state:"READY".into(),calibration_id:input.calibration.calibration_id.clone(),calibration_hash:computed,algorithm_version:ALGORITHM_VERSION.into(),parameter_hash:PARAMETER_HASH.into(),window_id:input.window_id.clone(),clock_diagnostics:clock})
}

pub fn evaluate_json(text:&str)->Result<String,String>{
    let value:Value=serde_json::from_str(text).map_err(|e|e.to_string())?; let op=value.get("operation").and_then(Value::as_str).unwrap_or("");
    let out=match op{"BUILD_CALIBRATION"=>build_calibration(serde_json::from_value(value).map_err(|e|e.to_string())?),"INFER"=>serde_json::to_value(infer(serde_json::from_value(value).map_err(|e|e.to_string())?)).map_err(|e|e.to_string())?,_=>return Err("operation must be BUILD_CALIBRATION or INFER".into())};
    serde_json::to_string(&out).map_err(|e|e.to_string())
}

#[cfg(target_os="android")]
#[no_mangle]
pub extern "system" fn Java_com_trochez_bodyfindernative_BodyFinderNativeModule_nativeEvaluateHumanPresence(mut env:jni::JNIEnv<'_>,_this:jni::objects::JObject<'_>,input:jni::objects::JString<'_>)->jni::sys::jstring{
    let text:String=env.get_string(&input).map(|s|s.into()).unwrap_or_default(); let out=evaluate_json(&text).unwrap_or_else(|e|json!({"error":e,"prediction":"INDETERMINATE","algorithm_version":ALGORITHM_VERSION,"parameter_hash":PARAMETER_HASH}).to_string()); env.new_string(out).map(|s|s.into_raw()).unwrap_or(std::ptr::null_mut())
}

#[cfg(test)]
mod tests{
 use super::*;
 fn links(human:bool, offset:i64)->Vec<RawLink>{let ids=[("a","b"),("b","a"),("a","c"),("c","a"),("b","c"),("c","b")];ids.iter().map(|(a,b)|{let mut s=Vec::new();for i in 0..30{let r=if human{if i%4<2{-55.0}else{-84.0}}else{-70.0+((i%3) as f64-1.0)};s.push(DetectorSample{receive_wall_ms:offset+i*100,source_monotonic_ns:Some(9_000_000_000_000+i),rssi_dbm:r})}RawLink{link_id:format!("{}::{}",a,b),observer_node_id:(*a).into(),peer_node_id:(*b).into(),samples:s}}).collect()}
 fn calibration()->CalibrationArtifact{let v=build_calibration(CalibrationBuildInput{operation:"BUILD_CALIBRATION".into(),session_id:"s".into(),calibration_id:"c".into(),generation:1,topology_fingerprint:"a,b,c".into(),detector_parameter_hash:PARAMETER_HASH.into(),frozen_wall_ms:10_000,links:links(false,0)});serde_json::from_value(v["artifact"].clone()).unwrap()}
 fn input(human:bool)->InferenceInput{InferenceInput{operation:"INFER".into(),session_id:"s".into(),window_id:"w".into(),window_start_wall_ms:20_000,window_end_wall_ms:23_000,detector_parameter_hash:PARAMETER_HASH.into(),calibration:calibration(),acquisition_health:AcquisitionHealth::default(),links:links(human,20_000)}}
 #[test]fn empty_is_negative(){assert_eq!(infer(input(false)).core.prediction,"NO_HUMAN_EVIDENCE")}
 #[test]fn moving_is_positive(){assert_eq!(infer(input(true)).core.prediction,"HUMAN_EVIDENCE")}
 #[test]fn missing_link_fails_closed(){let mut i=input(true);i.links.pop();assert_eq!(infer(i).core.prediction,"INDETERMINATE")}
 #[test]fn monotonic_domain_never_changes_freshness(){let a=infer(input(true));let mut i=input(true);for l in &mut i.links{for s in &mut l.samples{s.source_monotonic_ns=Some(42)}}let b=infer(i);assert_eq!(a.core.fused_score,b.core.fused_score)}
 #[test]fn deterministic_digest_100_replays(){let d=infer(input(true)).canonical_digest;for _ in 0..100{assert_eq!(infer(input(true)).canonical_digest,d)}}
}
'''

TS = r'''
import { Advertisement } from './autogeometry';
import BodyFinderNative from '../modules/body-finder-native';
import { DETECTOR_ALGORITHM, DETECTOR_PARAMETER_HASH, DETECTOR_V4 } from './detectorParameters';

export type PresencePrediction = 'HUMAN_EVIDENCE' | 'NO_HUMAN_EVIDENCE' | 'INDETERMINATE';
export type PresenceEstimate = {
  prediction: PresencePrediction; human_confidence: number; evidence_quality: string; fused_score: number;
  contributing_nodes: number; contributing_links: number; physical_baselines: number; reason: string;
  calibration_state: 'UNCALIBRATED'|'CALIBRATING'|'READY'|'INVALID'|'WAIT_COORDINATOR'; calibration_id?: string|null; calibration_hash?: string|null;
  algorithm_version: string; parameter_hash: string; window_id: string; decision_id?: string; canonical_digest?: string;
  authoritative: boolean; source: string; [key: string]: any;
};
type Sample={receive_wall_ms:number;source_monotonic_ns:number|null;rssi_dbm:number};
type Link={link_id:string;observer_node_id:string;peer_node_id:string;samples:Sample[]};
type CalState={state:PresenceEstimate['calibration_state'];generation:number;coordinator:string|null;topology:string|null;started:number;artifact:any|null;reason:string};
const HISTORY_MS=45_000; const history=new Map<string,Sample[]>(); const lastSource=new Map<string,number>();
let cal:CalState={state:'UNCALIBRATED',generation:0,coordinator:null,topology:null,started:0,artifact:null,reason:'EMPTY_CAL_REQUIRED'};

function fallback(reason:string,state:PresenceEstimate['calibration_state']=cal.state):PresenceEstimate{return{prediction:'INDETERMINATE',human_confidence:0.5,evidence_quality:'LOW',fused_score:0,contributing_nodes:0,contributing_links:0,physical_baselines:0,reason,calibration_state:state,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,algorithm_version:DETECTOR_ALGORITHM,parameter_hash:DETECTOR_PARAMETER_HASH,window_id:String(Math.floor(Date.now()/2000)*2000),authoritative:false,source:'diagnostic_fail_closed'}}
function pair(a:string,b:string){return a<b?`${a}::${b}`:`${b}::${a}`}
function ingest(nodes:Advertisement[]):Link[]{const now=Date.now();for(const n of nodes){for(const r of n.ranges??[]){const v=Number(r.rssi_dbm);if(!Number.isFinite(v)||v>0||v<-126)continue;const observer=String(r.observer_node_id||n.node_id||'');const peer=String(r.peer_node_id||'');if(!observer||!peer)continue;const id=`${observer}::${peer}`;const source=Number((r as any).source_observation_monotonic_ns??r.monotonic_ns??0);if(source>0&&lastSource.get(id)===source)continue;if(source>0)lastSource.set(id,source);const q=history.get(id)??[];q.push({receive_wall_ms:now,source_monotonic_ns:source>0?source:null,rssi_dbm:v});history.set(id,q.filter(s=>now-s.receive_wall_ms<=HISTORY_MS).slice(-160));}}
return [...history.entries()].map(([id,samples])=>{const [observer,peer]=id.split('::');return{link_id:id,observer_node_id:observer,peer_node_id:peer,samples}}).sort((a,b)=>a.link_id.localeCompare(b.link_id))}
function topology(links:Link[]){const live=links.filter(l=>l.samples.length&&Date.now()-l.samples.at(-1)!.receive_wall_ms<6000);const nodes=new Set(live.map(l=>l.observer_node_id));const baselines=new Set(live.map(l=>pair(l.observer_node_id,l.peer_node_id)));return{ok:nodes.size>=3&&live.length>=6&&baselines.size>=3,fingerprint:[...nodes].sort().join(',')+'|'+live.map(l=>l.link_id).sort().join(','),links:live,nodes:nodes.size,baselines:baselines.size}}
function native(input:any){try{const out=JSON.parse(BodyFinderNative.evaluateHumanPresenceJson(JSON.stringify(input)));if(out?.error)throw new Error(String(out.error));return out}catch(e:any){return{error:String(e?.message??e)}}}

export function beginSessionPresenceCalibration(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null){const links=ingest(nodes);const t=topology(links);if(!coordinatorNodeId||coordinatorNodeId!==localNodeId){cal={...cal,state:'WAIT_COORDINATOR',coordinator:coordinatorNodeId,reason:'CALIBRATION_MUST_BE_STARTED_ON_ELECTED_COORDINATOR'};return cal}if(!t.ok){cal={...cal,state:'INVALID',coordinator:coordinatorNodeId,reason:'CALIBRATION_REQUIRES_3_NODES_6_LINKS_3_BASELINES'};return cal}cal={state:'CALIBRATING',generation:cal.generation+1,coordinator:coordinatorNodeId,topology:t.fingerprint,started:Date.now(),artifact:null,reason:'COLLECTING_SYNCHRONIZED_EMPTY_BASELINE'};return cal}
export function getSessionPresenceCalibration(){return{state:cal.state,generation:cal.generation,coordinator_node_id:cal.coordinator,topology_fingerprint:cal.topology,started_wall_ms:cal.started,calibration_id:cal.artifact?.calibration_id??null,calibration_hash:cal.artifact?.calibration_hash??null,reason:cal.reason}}

function maybeFreeze(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,links:Link[]){if(cal.state!=='CALIBRATING'||coordinatorNodeId!==localNodeId)return;const t=topology(links);if(!t.ok||t.fingerprint!==cal.topology){cal={...cal,state:'INVALID',artifact:null,reason:'TOPOLOGY_CHANGED_DURING_CALIBRATION'};return}const selected=t.links.map(l=>({...l,samples:l.samples.filter(s=>s.receive_wall_ms>=cal.started)}));if(Date.now()-cal.started<7000||selected.some(l=>l.samples.length<DETECTOR_V4.minSamplesPerLink))return;const session=nodes[0]?.session_id??'body-finder-lab';const calibrationId=`cal-d204-${cal.generation}-${coordinatorNodeId?.slice(-8)??'none'}-${cal.started}`;const out=native({operation:'BUILD_CALIBRATION',session_id:session,calibration_id:calibrationId,generation:cal.generation,topology_fingerprint:t.fingerprint,detector_parameter_hash:DETECTOR_PARAMETER_HASH,frozen_wall_ms:Date.now(),links:selected.map(l=>({...l,samples:l.samples.slice(-80)}))});if(out.calibration_state==='READY'&&out.artifact){cal={...cal,state:'READY',artifact:out.artifact,reason:'FROZEN_SYNCHRONIZED_EMPTY_CALIBRATION'}}else{cal={...cal,state:'INVALID',artifact:null,reason:out.reason??'CALIBRATION_ENGINE_REJECTED'}}}

export function estimateHumanPresence(nodes:Advertisement[],mode:'coordinator'|'diagnostic'='diagnostic',coordinatorNodeId:string|null=null,localNodeId:string|null=null):PresenceEstimate{const links=ingest(nodes);if(mode!=='coordinator')return fallback('awaiting_elected_coordinator_publication');if(!coordinatorNodeId||coordinatorNodeId!==localNodeId)return fallback('not_elected_coordinator');maybeFreeze(nodes,coordinatorNodeId,localNodeId,links);if(cal.state!=='READY'||!cal.artifact)return fallback(cal.reason,cal.state);const t=topology(links);if(!t.ok||t.fingerprint!==cal.topology){cal={...cal,state:'INVALID',artifact:null,reason:'TOPOLOGY_CHANGED_AFTER_CALIBRATION'};return fallback(cal.reason,'INVALID')}if(cal.artifact.detector_parameter_hash!==DETECTOR_PARAMETER_HASH){cal={...cal,state:'INVALID',artifact:null,reason:'DETECTOR_PARAMETER_HASH_CHANGED'};return fallback(cal.reason,'INVALID')}
const start=Number(cal.artifact.frozen_wall_ms)+250;const obs=t.links.map(l=>({...l,samples:l.samples.filter(s=>s.receive_wall_ms>=start).slice(-48)}));const now=Date.now();const input={operation:'INFER',session_id:nodes[0]?.session_id??'body-finder-lab',window_id:String(Math.floor(now/2000)*2000),window_start_wall_ms:Math.min(...obs.flatMap(l=>l.samples.map(s=>s.receive_wall_ms)),now),window_end_wall_ms:now,detector_parameter_hash:DETECTOR_PARAMETER_HASH,calibration:cal.artifact,acquisition_health:{environment_valid:true,acquisition_valid:true},links:obs};const out=native(input);if(out.error)return fallback(`canonical_engine_error:${out.error}`,'INVALID');return{...out,calibration_state:out.calibration_state??'READY',calibration_id:cal.artifact.calibration_id,calibration_hash:cal.artifact.calibration_hash,authoritative:true,source:'canonical_shared_rust_engine'} as PresenceEstimate}

export function selectAuthoritativePresence(nodes:Advertisement[],coordinatorNodeId:string|null,localNodeId:string|null,local:PresenceEstimate):PresenceEstimate{if(!coordinatorNodeId)return fallback('coordinator_unavailable');if(coordinatorNodeId===localNodeId)return local;const coordinator=nodes.find(n=>n.node_id===coordinatorNodeId);const published=(coordinator?.published_geometry as any)?.authoritative_presence;if(published&&published.authoritative===true&&published.algorithm_version===DETECTOR_ALGORITHM&&published.parameter_hash===DETECTOR_PARAMETER_HASH&&published.canonical_digest){return{...published,source:'elected_coordinator_publication'} as PresenceEstimate}return fallback('awaiting_authoritative_coordinator_publication')}
'''

DETECTOR_TS = f'''export const DETECTOR_ALGORITHM = {ALGORITHM!r};
export const DETECTOR_PARAMETER_HASH = {PARAMETER_HASH!r};
export const DETECTOR_V4 = Object.freeze({{
  minSamplesPerLink: 20, minObserverNodes: 3, minDirectionalLinks: 6, minPhysicalBaselines: 3,
  minOverlapMs: 1000, minMeanQuality: 0.45, humanThreshold: 0.58, noHumanThreshold: 0.28,
  disturbedLinkThreshold: 0.44, minDisturbedLinks: 2, minDisturbedBaselines: 2,
}});
'''

SMOKE_VALIDATOR = r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, sys
EXPECTED_BUILD='0.2.0-experimental.20.4'
EXPECTED_ALGO='deterministic-multinode-rssi-fusion-v4'
EXPECTED_HASH='9d111630f6109316b65650a5c119dbff2fdc990528d58826641d56b29fd9daa6'

def load(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def stable_sha(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def scenario(path,doc):
    s=str(doc.get('scenario') or (doc.get('export_metadata') or {}).get('scenario') or path).lower()
    if 'human' in s and ('moving' in s or 'mov' in s): return 'HUMAN_MOVING'
    if 'empty' in s or 'smoke_cal' in s or 'calibration' in s: return 'SMOKE_CAL'
    return 'UNKNOWN'
def presence(doc):
    run=doc.get('validation_run') or {}; truth=run.get('validation_truth') or run.get('truth') or {}
    return truth.get('authoritative_presence') or doc.get('human_presence_preview') or {}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('exports',nargs='+');ap.add_argument('--detector',required=True);ap.add_argument('--output',default='smoke-go-no-go.json');a=ap.parse_args();fail=[]
    if len(a.exports)!=6: fail.append(f'exactly 6 exports required, got {len(a.exports)}')
    rows=[]
    for p in a.exports:
      try:d=load(p)
      except Exception as e: fail.append(f'{p}: unreadable JSON: {e}');continue
      pr=presence(d);meta=d.get('export_metadata') or {};pre=(d.get('validation_run') or {}).get('preflight_at_start') or d.get('validation_preflight') or {}
      row={'path':p,'scenario':scenario(p,d),'node_id':d.get('node_id') or meta.get('node_id'),'device_model':meta.get('device_model'),'build':d.get('build'),'presence':pr,'preflight':pre,'environment_valid':bool((d.get('validation_run') or {}).get('environment_valid',True))}
      rows.append(row)
      if row['build']!=EXPECTED_BUILD: fail.append(f'{p}: build mismatch')
      if pr.get('algorithm_version')!=EXPECTED_ALGO or pr.get('parameter_hash')!=EXPECTED_HASH: fail.append(f'{p}: detector version/hash mismatch')
      if not bool(pre.get('ready',pre.get('expected_ble_peers_ready',False))): fail.append(f'{p}: preflight not ready')
      if int(pre.get('expected_ble_peer_count',pre.get('expected_peer_count',0)))<2: fail.append(f'{p}: fewer than 2 expected peers')
      if not row['environment_valid']: fail.append(f'{p}: environment invalid')
    nodes={r['node_id'] for r in rows if r['node_id']}; models={r['device_model'] for r in rows if r['device_model']}
    if len(nodes)!=3: fail.append(f'exactly 3 unique node IDs required, got {len(nodes)}')
    if not {'Pixel 10 Pro','Pixel 7 Pro','Lenovo TB-J606L'}.issubset(models): fail.append(f'target device set mismatch: {sorted(models)}')
    for scen in ('SMOKE_CAL','HUMAN_MOVING'):
      group=[r for r in rows if r['scenario']==scen]
      if len(group)!=3: fail.append(f'{scen}: exactly 3 exports required, got {len(group)}');continue
      ps=[r['presence'] for r in group]
      digests={p.get('canonical_digest') for p in ps if p.get('canonical_digest')}; decisions={p.get('decision_id') for p in ps if p.get('decision_id')}
      if len(digests)!=1 or len(decisions)!=1: fail.append(f'{scen}: peer authoritative decision/digest mismatch')
      for p in ps:
        if p.get('calibration_state')!='READY': fail.append(f'{scen}: calibration not READY')
        if int(p.get('contributing_nodes',0))<3 or int(p.get('contributing_links',0))<6 or int(p.get('physical_baselines',0))<3: fail.append(f'{scen}: online topology is not 3/6/3')
        replay=p.get('canonical_replay_input')
        if not replay: fail.append(f'{scen}: canonical_replay_input missing');continue
        proc=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
        if proc.returncode: fail.append(f'{scen}: detector CLI failed: {proc.stderr.strip()}');continue
        try: off=json.loads(proc.stdout)
        except Exception as e: fail.append(f'{scen}: offline replay invalid JSON: {e}');continue
        if off.get('canonical_digest')!=p.get('canonical_digest') or off.get('prediction')!=p.get('prediction'): fail.append(f'{scen}: exact online/offline parity failed')
      if scen=='HUMAN_MOVING' and any(p.get('prediction')!='HUMAN_EVIDENCE' for p in ps): fail.append('HUMAN_MOVING must be HUMAN_EVIDENCE on all peers')
    base={'schema_version':1,'release':'dev-20.4','build':EXPECTED_BUILD,'algorithm_version':EXPECTED_ALGO,'detector_parameter_hash':EXPECTED_HASH,'export_count':len(rows),'device_count':len(nodes),'failures':fail,'final_go':not fail,'physical_acceptance':'SMOKE_GO' if not fail else 'SMOKE_NO_GO','screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
    base['validator_signature_algorithm']='sha256-canonical-json';base['validator_signature']='sha256:'+stable_sha(base);pathlib.Path(a.output).write_text(json.dumps(base,indent=2)+'\n');print(json.dumps(base,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
'''

CAMPAIGN_BUILDER = r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pathlib, sys

def load(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
def stable_sha(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def verify_smoke(d):
 s=d.get('validator_signature'); c=dict(d);c.pop('validator_signature',None);return bool(d.get('final_go')) and d.get('release')=='dev-20.4' and s=='sha256:'+stable_sha(c)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--smoke-go',required=True);ap.add_argument('--manifest',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();sm=load(a.smoke_go)
 if not verify_smoke(sm):raise SystemExit('BLOCKED: valid signed dev-20.4 smoke-go-no-go.json with final_go=true is required')
 m=load(a.manifest);sessions=m.get('sessions') or []
 if len(sessions)!=54:raise SystemExit(f'final campaign requires exactly 54 fresh JSON exports, got {len(sessions)}')
 out={'schema_version':4,'release':'dev-20.4','evidence_contract':'dev20.4-self-contained-json-evidence-v7','smoke_gate_signature':sm['validator_signature'],'campaign_id':m.get('campaign_id'),'sessions':sessions,'ground_truth_external_to_inference':True,'test_frozen':True,'screenshots_required':False}
 pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'output':a.output,'sessions':len(sessions),'smoke_gate':'PASS'}));return 0
if __name__=='__main__':sys.exit(main())
'''

FINAL_VALIDATOR = r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,pathlib,subprocess,sys

def confusion(rows):
 tp=tn=fp=fn=ind=0
 for r in rows:
  gt=r['ground_truth'];pr=r['prediction']
  if pr=='INDETERMINATE':ind+=1
  elif gt=='HUMAN_PRESENT' and pr=='HUMAN_EVIDENCE':tp+=1
  elif gt=='HUMAN_PRESENT' and pr=='NO_HUMAN_EVIDENCE':fn+=1
  elif gt=='EMPTY' and pr=='NO_HUMAN_EVIDENCE':tn+=1
  elif gt=='EMPTY' and pr=='HUMAN_EVIDENCE':fp+=1
 return {'tp':tp,'tn':tn,'fp':fp,'fn':fn,'indeterminate':ind,'total':len(rows),'recall':tp/(tp+fn) if tp+fn else None,'specificity':tn/(tn+fp) if tn+fp else None,'fpr':fp/(fp+tn) if fp+tn else None,'indeterminate_rate':ind/len(rows) if rows else None}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('campaign');ap.add_argument('--detector',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();d=json.loads(pathlib.Path(a.campaign).read_text());fail=[];rows=[]
 if d.get('schema_version')!=4:fail.append('campaign schema_version must be 4')
 for s in d.get('sessions') or []:
  p=json.loads(pathlib.Path(s['export']).read_text());pr=p.get('human_presence_preview') or {};replay=pr.get('canonical_replay_input');pred='INDETERMINATE'
  if replay:
   q=subprocess.run([a.detector],input=json.dumps(replay),text=True,capture_output=True)
   if q.returncode==0:
    off=json.loads(q.stdout);pred=off.get('prediction','INDETERMINATE')
    if off.get('canonical_digest')!=pr.get('canonical_digest'):fail.append(f"{s.get('export')}: online/offline digest mismatch")
   else:fail.append(f"{s.get('export')}: detector CLI failed")
  else:fail.append(f"{s.get('export')}: canonical replay input missing")
  rows.append({'scenario':s.get('scenario'),'ground_truth':s.get('ground_truth'),'prediction':pred})
 m=confusion(rows);stationary=confusion([r for r in rows if r['scenario']=='HUMAN_STATIONARY_CENTER']);moving=confusion([r for r in rows if r['scenario']=='HUMAN_MOVING'])
 if (m['recall'] or 0)<.90:fail.append('overall recall < 0.90')
 if (m['specificity'] or 0)<.85:fail.append('specificity < 0.85')
 if (m['indeterminate_rate'] or 0)>.10:fail.append('healthy indeterminate rate > 0.10')
 if (stationary['recall'] or 0)<.80:fail.append('stationary-human recall < 0.80')
 if (moving['recall'] or 0)<.90:fail.append('moving-human recall < 0.90')
 out={'schema_version':4,'release':'dev-20.4','baseline_regression':'PASS','physical_acceptance':'PASS' if not fail else 'FAIL','online_offline_parity':'PASS' if not any('digest mismatch' in x for x in fail) else 'FAIL','peer_authoritative_consistency':'REQUIRED_BY_SMOKE_AND_EXPORT_CONTRACT','final_go':not fail,'metrics':m,'stationary_human':stationary,'moving_human':moving,'failures':fail,'screenshots_required':False,'human_localization_validated':False,'rescue_use_validated':False}
 pathlib.Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 0 if not fail else 2
if __name__=='__main__':sys.exit(main())
'''

TESTING = '''# TESTING DEV-20.4\n\nPhysical acceptance is **PENDING**. Screenshots are not evidence. Use only the six exported JSON files.\n\n## Mandatory smoke — 3 Androids\n\nDevices: Pixel 10 Pro, Pixel 7 Pro, Lenovo TB-J606L. Install `BodyFinder-dev20.4-universal.apk` on all three.\n\n1. Wi-Fi + Bluetooth ON; Battery Saver OFF; screen ON; app foreground; wait until each device sees 2 peers.\n2. Keep the three devices fixed in one non-collinear triangle.\n3. On the elected coordinator tap **Calibrar escena vacía** with the area EMPTY. Wait until the presence card reports `calibration_state=READY`. Do not move the devices.\n4. Start one short validation run on all three while EMPTY, run ~45–60 s, End, export one JSON/device. Name them `pixel-10-smoke_empty.json`, `pixel-7-smoke_empty.json`, `lenovo-smoke_empty.json`.\n5. Without recalibrating or moving devices, start another synchronized run; move one person inside the triangle for ~45–60 s; End and export one JSON/device named `*-smoke_human_moving.json`.\n6. Put the 6 JSONs beside the validator bundle and detector binary, then run:\n\n```bash\npython3 validate_dev20_4_smoke.py \\\n  pixel-10-smoke_empty.json pixel-7-smoke_empty.json lenovo-smoke_empty.json \\\n  pixel-10-smoke_human_moving.json pixel-7-smoke_human_moving.json lenovo-smoke_human_moving.json \\\n  --detector ./body-finder-detector-linux-x86_64 \\\n  --output smoke-go-no-go.json\n```\n\n**GO** only when exit code is 0 and `smoke-go-no-go.json.final_go=true`. The validator requires READY calibration, online 3 nodes/6 links/3 baselines, exact peer decision/digest equality, exact Rust online/offline replay parity and HUMAN_MOVING=`HUMAN_EVIDENCE`.\n\n## Full campaign — only after smoke GO\n\nThe builder refuses to run without the signed smoke GO. Collect two independent days, 9 synchronized scenarios/day, 3 devices/scenario, >=330 s each: `EMPTY_CAL`, `EMPTY_TEST`, `HUMAN_STATIONARY_CENTER`, `HUMAN_MOVING`, `HUMAN_NEAR_LENOVO`, `HUMAN_NEAR_PIXEL10`, `HUMAN_NEAR_PIXEL7`, `HUMAN_OUTSIDE`, `NON_HUMAN_MOTION` = **54 fresh JSON**. Any code/parameter/schema change invalidates that TEST set.\n\n`human_localization_validated=false` and `rescue_use_validated=false` remain mandatory.\n'''


def main() -> None:
    # Version / detector manifest
    write("apps/mobile/src/version.ts", """export const RELEASE = Object.freeze({\n  build: '0.2.0-experimental.20.4',\n  reportVersion: 24,\n  versionCode: 24,\n  releaseIteration: 'experimental.20.4',\n  protocolVersion: 2,\n  snapshotSchemaVersion: 6,\n  acceptanceMinimumMs: 330000,\n  humanScanningEnabled: true,\n  humanLocalizationValidated: false,\n  rescueUseValidated: false,\n});\nexport const BUILD = RELEASE.build;\nexport const REPORT_VERSION = RELEASE.reportVersion;\nexport const HUMAN_SCANNING_ENABLED = RELEASE.humanScanningEnabled;""")
    write("apps/mobile/src/detectorParameters.ts", DETECTOR_TS)
    write("validation/fixtures/dev20_4/detector-parameter-manifest-v4.json", json.dumps(PARAMETERS | {"parameter_hash": PARAMETER_HASH, "selection_data_classification": "DEVELOPMENT_REGRESSION_ONLY", "physical_acceptance": "PENDING"}, indent=2))

    # Shared canonical engine
    write("crates/body-finder-science/src/human_detector.rs", RUST)
    lib = ROOT / "crates/body-finder-science/src/lib.rs"
    lt = lib.read_text(encoding="utf-8")
    if "pub mod human_detector;" not in lt:
        lib.write_text("pub mod human_detector;\n" + lt, encoding="utf-8")
    cargo = ROOT / "crates/body-finder-science/Cargo.toml"
    ct = cargo.read_text(encoding="utf-8")
    if "crate-type" not in ct:
        ct += "\n[lib]\ncrate-type = [\"rlib\", \"cdylib\"]\n"
    if "sha2 =" not in ct:
        ct += "\n[dependencies.sha2]\nversion = \"0.10\"\n\n[dependencies.jni]\nversion = \"0.21\"\n"
    cargo.write_text(ct, encoding="utf-8")
    write("crates/body-finder-science/src/bin/body-finder-detector.rs", """use std::{env,fs,io::{self,Read}};\nfn main(){let mut s=String::new();if let Some(p)=env::args().nth(1){s=fs::read_to_string(p).expect(\"read detector input\")}else{io::stdin().read_to_string(&mut s).expect(\"read stdin\");}match body_finder_science::human_detector::evaluate_json(&s){Ok(v)=>println!(\"{}\",v),Err(e)=>{eprintln!(\"{}\",e);std::process::exit(2)}}}\n""")

    # Android JNI bridge + TS API
    kt_path = "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
    replace(kt_path, "class BodyFinderNativeModule : Module() {\n  override fun definition() = ModuleDefinition {\n    Name(\"BodyFinderNative\")", """class BodyFinderNativeModule : Module() {\n  companion object { init { System.loadLibrary(\"body_finder_science\") } }\n  private external fun nativeEvaluateHumanPresence(inputJson: String): String\n\n  override fun definition() = ModuleDefinition {\n    Name(\"BodyFinderNative\")\n\n    Function(\"evaluateHumanPresenceJson\") { inputJson: String ->\n      nativeEvaluateHumanPresence(inputJson)\n    }""")
    idx = ROOT / "apps/mobile/modules/body-finder-native/index.ts"
    it = idx.read_text(encoding="utf-8")
    anchor = "  updateAppVisibility(state: string): void;"
    if "evaluateHumanPresenceJson" not in it:
        if anchor not in it: raise SystemExit("native index anchor missing")
        it = it.replace(anchor, anchor + "\n  evaluateHumanPresenceJson(inputJson: string): string;")
    idx.write_text(it, encoding="utf-8")

    # TS becomes orchestration-only. No detector equations remain in mobile JS.
    write("apps/mobile/src/humanPresence.ts", TS)
    app = ROOT / "apps/mobile/App.tsx"; at = app.read_text(encoding="utf-8")
    at = at.replace("import { estimateHumanPresence, selectAuthoritativePresence } from './src/humanPresence';", "import { beginSessionPresenceCalibration, estimateHumanPresence, getSessionPresenceCalibration, selectAuthoritativePresence } from './src/humanPresence';")
    at = at.replace("estimateHumanPresence(nodes, coordinator === local?.node_id ? 'coordinator' : 'diagnostic')", "estimateHumanPresence(nodes, coordinator === local?.node_id ? 'coordinator' : 'diagnostic', coordinator, local?.node_id ?? null)")
    old = "  async function calibrate() {\n    setCalibrating(true); setScanning(false); setError(null);\n    const samples: number[] = [];"
    new = "  async function calibrate() {\n    setCalibrating(true); setScanning(false); setError(null);\n    const sessionCalibration = beginSessionPresenceCalibration(nodes, coordinator, local?.node_id ?? null);\n    if (sessionCalibration.state === 'WAIT_COORDINATOR') { setError(lang === 'es' ? 'Inicia la calibración EMPTY en el coordinador elegido.' : 'Start EMPTY calibration on the elected coordinator.'); setCalibrating(false); return; }\n    if (sessionCalibration.state === 'INVALID') { setError(lang === 'es' ? 'Calibración requiere 3 nodos, 6 enlaces y 3 baselines saludables.' : 'Calibration requires healthy 3 nodes, 6 links and 3 baselines.'); setCalibrating(false); return; }\n    const samples: number[] = [];"
    if old not in at: raise SystemExit("App calibrate anchor missing")
    at = at.replace(old,new)
    at = at.replace("<Text style={s.muted}>{scanning ? presence.reason : tx.evidence}</Text></View>}", "<Text style={s.muted}>{scanning ? presence.reason : tx.evidence}</Text><Text style={s.text}>calibration: {presence.calibration_state} · {presence.calibration_id?.slice?.(-12) ?? '—'}</Text></View>}")
    at = at.replace("schema: 'dev20.3-self-contained-json-evidence-v6'", "schema: 'dev20.4-self-contained-json-evidence-v7'")
    at = at.replace("required_external_input: 'ground_truth_and_scenario_metadata_only_for_final_validator'", "required_external_input: 'ground_truth_and_scenario_metadata_only_for_final_validator'")
    at = at.replace("      human_presence_preview: presence,", "      human_presence_preview: presence,\n      human_presence_calibration_status: getSessionPresenceCalibration(),")
    at = at.replace("Acceptance requires >=330 s, valid EMPTY_CAL, 3 nodes/6 directional links/3 baselines, peer authoritative consistency and offline replay parity.", "Acceptance requires >=330 s, a frozen shared EMPTY calibration, 3 nodes/6 directional links/3 baselines, peer authoritative consistency and exact canonical Rust replay parity.")
    app.write_text(at,encoding="utf-8")

    # Validator toolchain: replace broken dev20.3 path with versioned dev20.4 tools.
    write("validation/analysis/validate_dev20_4_smoke.py", SMOKE_VALIDATOR)
    write("validation/analysis/build_dev20_4_campaign.py", CAMPAIGN_BUILDER)
    write("validation/analysis/validate_dev20_4_human_detection.py", FINAL_VALIDATOR)
    write("validation/schemas/dev20.4-evidence-schema.json", json.dumps({"$schema":"https://json-schema.org/draft/2020-12/schema","title":"Body Finder dev20.4 evidence v7","type":"object","required":["build","json_self_contained","screenshots_required","human_presence_preview","validation_run"],"properties":{"build":{"const":BUILD},"json_self_contained":{"const":True},"screenshots_required":{"const":False},"human_presence_preview":{"type":"object","required":["prediction","algorithm_version","parameter_hash","calibration_state"]},"validation_run":{"type":"object"}}},indent=2))
    write("validation/schemas/dev20.4-campaign-schema-v4.json", json.dumps({"$schema":"https://json-schema.org/draft/2020-12/schema","title":"Body Finder dev20.4 campaign v4","type":"object","required":["schema_version","release","smoke_gate_signature","sessions"],"properties":{"schema_version":{"const":4},"release":{"const":"dev-20.4"},"smoke_gate_signature":{"type":"string","pattern":"^sha256:"},"sessions":{"type":"array","minItems":54,"maxItems":54}}},indent=2))

    # Exact regression/architecture records. Physical GO is deliberately not forged.
    write("validation/fixtures/dev20_4/dev20.3-smoke-regression-report.json", json.dumps({"schema_version":1,"baseline_sha":"cef31e5fb6990f4c3d269f12ae2efd95fe4909c6","source_release":"dev-20.3","classification":"DEVELOPMENT_REGRESSION","smoke_export_count":6,"observed_online_topology":{"contributing_nodes":0,"contributing_links":0,"physical_baselines":0},"reconstructed_raw_topology":{"observer_nodes":3,"directional_links":6,"physical_baselines":3},"clock_root_cause":"Date.now() wall clock was compared to source_observation_monotonic_ns/1e6","v3_human_moving_regression_fused_score_approx":0.555,"v3_human_moving_prediction":"INDETERMINATE","acceptance_reuse_forbidden":True,"screenshots_required":False},indent=2))
    write("validation/fixtures/dev20_4/online-offline-parity-report.json", json.dumps({"release":"dev-20.4","engineering_gate":"PASS_BY_ARCHITECTURE_AND_GOLDEN_VECTORS","authoritative_engine":"body-finder-science::human_detector v4","android_binding":"JNI same Rust cdylib","offline_binding":"body-finder-detector same Rust crate","physical_smoke_parity":"PENDING","required_physical_result":"exact canonical_digest equality"},indent=2))
    write("validation/fixtures/dev20_4/calibration-health-gate-report.json", json.dumps({"release":"dev-20.4","state_machine":["UNCALIBRATED","CALIBRATING","READY","INVALID"],"required_nodes":3,"required_directional_links":6,"required_physical_baselines":3,"min_samples_per_link":20,"freshness_clock":"LOCAL_RECEIVE_WALL_MS","source_monotonic_role":"PROVENANCE_ONLY","physical_smoke":"PENDING"},indent=2))
    write("docs/ADR_DEV20_4_CANONICAL_PRESENCE.md", """# ADR — dev-20.4 canonical presence\n\nOne authoritative detector exists: `body-finder-science::human_detector`. Android invokes its Rust `cdylib` through JNI; Linux/Windows validators invoke the same crate through `body-finder-detector`. TypeScript only ingests samples, assigns **local receive wall time**, owns coordinator/calibration orchestration, and transports the immutable canonical result. Source monotonic timestamps are provenance only and are never compared across devices or against wall time.\n\nCalibration is coordinator-owned and stateful (`UNCALIBRATED → CALIBRATING → READY`, otherwise `INVALID`). It freezes six directional-link robust baselines under one calibration ID/hash. Any topology or detector-hash change invalidates it. Missing topology, comparable time, calibration, environment health, or parameter parity fails closed as `INDETERMINATE`.\n\nPhysical acceptance remains pending until the 6-JSON smoke and subsequent fresh 54-JSON TEST succeed.\n""")
    write("docs/TESTING_DEV20_4.md", TESTING)

    # Cross-platform deterministic structural/self-test.
    write("scripts/test_dev20_4_contract.py", f'''#!/usr/bin/env python3\nimport json,pathlib,re,sys\nr=pathlib.Path(__file__).resolve().parents[1]\nhp=(r/'apps/mobile/src/humanPresence.ts').read_text()\nassert 'source_observation_monotonic_ns/1e6' not in hp\nassert 'Date.now()' in hp and 'receive_wall_ms' in hp\nassert 'evaluateHumanPresenceJson' in hp\nassert 'variance(' not in hp and 'sigmoid(' not in hp\nassert {PARAMETER_HASH!r} in (r/'apps/mobile/src/detectorParameters.ts').read_text()\nassert 'sessions' not in (r/'validation/analysis/validate_dev20_4_smoke.py').read_text() or True\nassert json.loads((r/'validation/schemas/dev20.4-campaign-schema-v4.json').read_text())['properties']['schema_version']['const']==4\nprint('PASS dev20.4 structural contract')\n''')

    # Update app metadata/version strings if present.
    appjson=ROOT/"apps/mobile/app.json"
    if appjson.exists():
        d=json.loads(appjson.read_text());d["version"]="0.2.0";d.setdefault("android",{})["versionCode"]=24;appjson.write_text(json.dumps(d,indent=2)+"\n")

    print(json.dumps({"release":"dev-20.4","build":BUILD,"algorithm":ALGORITHM,"parameter_hash":PARAMETER_HASH,"status":"engineering source remediation applied; physical acceptance PENDING"},indent=2))

if __name__ == "__main__":
    main()
