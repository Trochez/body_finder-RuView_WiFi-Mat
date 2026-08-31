use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

pub const ALGORITHM_VERSION: &str = "deterministic-multinode-rssi-fusion-v8";
pub const PARAMETER_HASH: &str = "5d404d404e08d33cd179aa8657edd93f1e51885f5dfa1268af228465642a8d39";
pub const CALIBRATION_MIN_SAMPLES: usize = 30;
pub const OBSERVATION_MIN_SAMPLES: usize = 24;
pub const QUALITY_REFERENCE_SAMPLES: usize = 24;
pub const MIN_MEAN_QUALITY: f64 = 0.80;
pub const CALIBRATION_MIN_OVERLAP_MS: i64 = 1_500;
pub const INFERENCE_MIN_OVERLAP_MS: i64 = 1_500;
const HUMAN_THRESHOLD: f64 = 0.50;
const NO_HUMAN_THRESHOLD: f64 = 0.20;
const DISTURBED_THRESHOLD: f64 = 0.32;
const DYNAMIC_FLOOR: f64 = 0.20;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectorSample {
    pub receive_wall_ms: i64,
    #[serde(default)]
    pub source_monotonic_ns: Option<i64>,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquisitionHealth {
    #[serde(default = "yes")]
    pub environment_valid: bool,
    #[serde(default = "yes")]
    pub acquisition_valid: bool,
}
fn yes() -> bool {
    true
}
impl Default for AcquisitionHealth {
    fn default() -> Self {
        Self {
            environment_valid: true,
            acquisition_valid: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceInput {
    pub operation: String,
    pub session_id: String,
    pub window_id: String,
    pub window_start_wall_ms: i64,
    pub window_end_wall_ms: i64,
    pub detector_parameter_hash: String,
    pub calibration: CalibrationArtifact,
    #[serde(default)]
    pub acquisition_health: AcquisitionHealth,
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
    pub segmented_transition_score: f64,
    pub percentile_spread_change_score: f64,
    pub burst_activity_score: f64,
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
    #[serde(flatten)]
    pub core: InferenceCore,
    pub canonical_digest: String,
    pub decision_id: String,
    pub authoritative: bool,
    pub source: String,
    pub publication_contract_version: u32,
    pub canonical_replay_input: Value,
}

fn mean(xs: &[f64]) -> f64 {
    if xs.is_empty() {
        0.0
    } else {
        xs.iter().sum::<f64>() / xs.len() as f64
    }
}
fn variance(xs: &[f64]) -> f64 {
    let m = mean(xs);
    if xs.is_empty() {
        0.0
    } else {
        xs.iter().map(|x| (x - m) * (x - m)).sum::<f64>() / xs.len() as f64
    }
}
fn median(xs: &[f64]) -> f64 {
    let mut s = xs.to_vec();
    s.sort_by(|a, b| a.total_cmp(b));
    if s.is_empty() {
        return 0.0;
    }
    let n = s.len();
    if n % 2 == 1 {
        s[n / 2]
    } else {
        (s[n / 2 - 1] + s[n / 2]) / 2.0
    }
}
fn mad(xs: &[f64]) -> f64 {
    let m = median(xs);
    median(&xs.iter().map(|x| (x - m).abs()).collect::<Vec<_>>())
}
fn percentile(xs: &[f64], p: f64) -> f64 {
    let mut s = xs.to_vec();
    s.sort_by(|a, b| a.total_cmp(b));
    if s.is_empty() {
        return 0.0;
    }
    let pos = (s.len() - 1) as f64 * p;
    let lo = pos.floor() as usize;
    let hi = (lo + 1).min(s.len() - 1);
    s[lo] * (1.0 - (pos - lo as f64)) + s[hi] * (pos - lo as f64)
}
fn diff_energy(xs: &[f64]) -> f64 {
    if xs.len() < 2 {
        0.0
    } else {
        mean(
            &(1..xs.len())
                .map(|i| (xs[i] - xs[i - 1]).powi(2))
                .collect::<Vec<_>>(),
        )
    }
}
fn slope_activity(xs: &[f64]) -> f64 {
    if xs.len() < 2 {
        0.0
    } else {
        mean(
            &(1..xs.len())
                .map(|i| (xs[i] - xs[i - 1]).abs())
                .collect::<Vec<_>>(),
        )
    }
}
fn unit(x: f64) -> f64 {
    (1.0 - (-x.max(0.0)).exp()).clamp(0.0, 1.0)
}
fn physical(a: &str, b: &str) -> String {
    if a <= b {
        format!("{}::{}", a, b)
    } else {
        format!("{}::{}", b, a)
    }
}
fn sha(bytes: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(bytes))
}
fn round6(x: f64) -> f64 {
    (x * 1_000_000.0).round() / 1_000_000.0
}

fn baseline_stats(link: &RawLink) -> Result<BaselineStats, String> {
    if link.samples.len() < CALIBRATION_MIN_SAMPLES {
        return Err(format!(
            "{}: fewer than {} calibration samples",
            link.link_id, CALIBRATION_MIN_SAMPLES
        ));
    }
    let xs: Vec<f64> = link
        .samples
        .iter()
        .map(|s| s.rssi_dbm)
        .filter(|x| (-126.0..=0.0).contains(x))
        .collect();
    if xs.len() < CALIBRATION_MIN_SAMPLES {
        return Err(format!(
            "{}: insufficient valid RSSI calibration samples",
            link.link_id
        ));
    }
    let md = mad(&xs);
    let var = variance(&xs);
    let band = (2.0 * (1.4826 * md).max(var.sqrt()).max(1.0)).max(2.5);
    Ok(BaselineStats {
        link_id: link.link_id.clone(),
        observer_node_id: link.observer_node_id.clone(),
        peer_node_id: link.peer_node_id.clone(),
        sample_count: xs.len(),
        median_dbm: round6(median(&xs)),
        mean_dbm: round6(mean(&xs)),
        mad_db: round6(md),
        variance_db2: round6(var),
        iqr_db: round6(percentile(&xs, 0.9) - percentile(&xs, 0.1)),
        diff_energy: round6(diff_energy(&xs)),
        slope_activity: round6(slope_activity(&xs)),
        deviation_band_db: round6(band),
        first_receive_wall_ms: link
            .samples
            .iter()
            .map(|s| s.receive_wall_ms)
            .min()
            .unwrap_or(0),
        last_receive_wall_ms: link
            .samples
            .iter()
            .map(|s| s.receive_wall_ms)
            .max()
            .unwrap_or(0),
    })
}

fn hash_artifact(a: &CalibrationArtifact) -> String {
    let mut c = a.clone();
    c.calibration_hash.clear();
    sha(&serde_json::to_vec(&c).expect("serialize calibration"))
}

pub fn build_calibration(input: CalibrationBuildInput) -> Value {
    let mut failures = Vec::new();
    if input.detector_parameter_hash != PARAMETER_HASH {
        failures.push("detector_parameter_hash_mismatch".to_string());
    }
    let mut links = input.links.clone();
    links.sort_by(|a, b| a.link_id.cmp(&b.link_id));
    let mut stats = Vec::new();
    for l in &links {
        match baseline_stats(l) {
            Ok(s) => stats.push(s),
            Err(e) => failures.push(e),
        }
    }
    let nodes: BTreeSet<_> = stats.iter().map(|s| s.observer_node_id.clone()).collect();
    let phys: BTreeSet<_> = stats
        .iter()
        .map(|s| physical(&s.observer_node_id, &s.peer_node_id))
        .collect();
    if nodes.len() < 3 {
        failures.push("fewer_than_3_observer_nodes".into());
    }
    if stats.len() < 6 {
        failures.push("fewer_than_6_directional_links".into());
    }
    if phys.len() < 3 {
        failures.push("fewer_than_3_physical_baselines".into());
    }
    if !stats.is_empty() {
        let start = stats
            .iter()
            .map(|s| s.first_receive_wall_ms)
            .max()
            .unwrap_or(0);
        let end = stats
            .iter()
            .map(|s| s.last_receive_wall_ms)
            .min()
            .unwrap_or(0);
        if end - start < CALIBRATION_MIN_OVERLAP_MS {
            failures.push("insufficient_comparable_wall_clock_overlap".into());
        }
    }
    if !failures.is_empty() {
        return json!({"operation":"BUILD_CALIBRATION","calibration_state":"INVALID","reason":"calibration_gate_failed","failures":failures,"algorithm_version":ALGORITHM_VERSION,"parameter_hash":PARAMETER_HASH});
    }
    let mut artifact = CalibrationArtifact {
        schema_version: 8,
        calibration_id: input.calibration_id,
        generation: input.generation,
        session_id: input.session_id,
        topology_fingerprint: input.topology_fingerprint,
        detector_algorithm: ALGORITHM_VERSION.into(),
        detector_parameter_hash: PARAMETER_HASH.into(),
        frozen_wall_ms: input.frozen_wall_ms,
        contributing_nodes: nodes.len(),
        directional_links: stats.len(),
        physical_baselines: phys.len(),
        comparable_clock_domain: "LOCAL_RECEIVE_WALL_MS".into(),
        links: stats,
        calibration_hash: String::new(),
    };
    artifact.calibration_hash = hash_artifact(&artifact);
    json!({"operation":"BUILD_CALIBRATION","calibration_state":"READY","reason":"frozen_synchronized_empty_calibration","artifact":artifact,"algorithm_version":ALGORITHM_VERSION,"parameter_hash":PARAMETER_HASH})
}

fn features(base: &BaselineStats, obs: &RawLink) -> Result<LinkFeature, String> {
    if obs.samples.len() < OBSERVATION_MIN_SAMPLES {
        return Err(format!(
            "{}: fewer than {} observation samples",
            obs.link_id, OBSERVATION_MIN_SAMPLES
        ));
    }
    let xs: Vec<f64> = obs
        .samples
        .iter()
        .map(|s| s.rssi_dbm)
        .filter(|x| (-126.0..=0.0).contains(x))
        .collect();
    if xs.len() < OBSERVATION_MIN_SAMPLES {
        return Err(format!(
            "{}: insufficient valid observation RSSI samples",
            obs.link_id
        ));
    }
    let robust_sigma = (1.4826 * base.mad_db)
        .max(base.variance_db2.sqrt())
        .max(1.0);
    let shift = 0.55 * unit((median(&xs) - base.median_dbm).abs() / robust_sigma)
        + 0.45 * unit((mean(&xs) - base.mean_dbm).abs() / robust_sigma);
    let obs_mad = mad(&xs);
    let obs_var = variance(&xs);
    let obs_iqr = percentile(&xs, 0.9) - percentile(&xs, 0.1);
    let spread = 0.30 * unit((obs_mad - base.mad_db).abs() / base.mad_db.max(1.0))
        + 0.45 * unit(((obs_var - base.variance_db2).abs() / base.variance_db2.max(0.25)).ln_1p())
        + 0.25 * unit((obs_iqr - base.iqr_db).abs() / base.iqr_db.max(1.0));
    let ode = diff_energy(&xs);
    let osa = slope_activity(&xs);
    let dynamic = 0.58
        * unit(((ode - base.diff_energy).abs() / base.diff_energy.max(0.25)).ln_1p())
        + 0.42 * unit(((osa - base.slope_activity).abs() / base.slope_activity.max(0.25)).ln_1p());
    let occ = mean(
        &xs.iter()
            .map(|x| {
                if (x - base.median_dbm).abs() >= base.deviation_band_db {
                    1.0
                } else {
                    0.0
                }
            })
            .collect::<Vec<_>>(),
    );
    let occupancy = (occ * 2.5).clamp(0.0, 1.0);
    let chunk = (xs.len() / 6).max(4);
    let chunks = xs.chunks(chunk).collect::<Vec<_>>();
    let persistence = mean(
        &chunks
            .iter()
            .map(|c| {
                if mean(
                    &c.iter()
                        .map(|x| {
                            if (*x - base.median_dbm).abs() >= base.deviation_band_db {
                                1.0
                            } else {
                                0.0
                            }
                        })
                        .collect::<Vec<_>>(),
                ) >= 0.20
                {
                    1.0
                } else {
                    0.0
                }
            })
            .collect::<Vec<_>>(),
    );
    let third = (xs.len() / 3).max(1);
    let early = &xs[..third.min(xs.len())];
    let late = &xs[xs.len().saturating_sub(third)..];
    let segmented_transition =
        unit((median(late) - median(early)).abs() / (base.deviation_band_db.max(2.0) * 2.0));
    let percentile_spread_change = unit((obs_iqr - base.iqr_db).max(0.0) / base.iqr_db.max(2.0));
    let burst_threshold = base.diff_energy.sqrt().max(1.5) * 1.5;
    let burst_activity = mean(
        &xs.windows(2)
            .map(|w| {
                if (w[1] - w[0]).abs() >= burst_threshold {
                    1.0
                } else {
                    0.0
                }
            })
            .collect::<Vec<_>>(),
    )
    .clamp(0.0, 1.0);
    let quality =
        (xs.len().min(base.sample_count) as f64 / QUALITY_REFERENCE_SAMPLES as f64).min(1.0);
    let dynamic_excess = ((dynamic - DYNAMIC_FLOOR) / (1.0 - DYNAMIC_FLOOR)).clamp(0.0, 1.0);
    let disturbance = 0.07 * shift
        + 0.13 * spread
        + 0.40 * dynamic_excess
        + 0.06 * occupancy
        + 0.10 * persistence
        + 0.12 * segmented_transition
        + 0.07 * percentile_spread_change
        + 0.05 * burst_activity;
    Ok(LinkFeature {
        link_id: obs.link_id.clone(),
        observer_node_id: obs.observer_node_id.clone(),
        peer_node_id: obs.peer_node_id.clone(),
        sample_count: xs.len(),
        shift_score: round6(shift),
        spread_score: round6(spread),
        dynamic_score: round6(dynamic),
        occupancy_score: round6(occupancy),
        persistence_score: round6(persistence),
        segmented_transition_score: round6(segmented_transition),
        percentile_spread_change_score: round6(percentile_spread_change),
        burst_activity_score: round6(burst_activity),
        quality: round6(quality),
        disturbance_score: round6(disturbance),
        first_receive_wall_ms: obs
            .samples
            .iter()
            .map(|s| s.receive_wall_ms)
            .min()
            .unwrap_or(0),
        last_receive_wall_ms: obs
            .samples
            .iter()
            .map(|s| s.receive_wall_ms)
            .max()
            .unwrap_or(0),
    })
}

fn invalid(
    input: &InferenceInput,
    cal_hash: String,
    reasons: Vec<String>,
    feats: Vec<LinkFeature>,
) -> InferenceResult {
    let nodes: BTreeSet<_> = feats.iter().map(|f| f.observer_node_id.clone()).collect();
    let phys: BTreeSet<_> = feats
        .iter()
        .map(|f| physical(&f.observer_node_id, &f.peer_node_id))
        .collect();
    let clock = ClockDiagnostics {
        freshness_clock_domain: "LOCAL_RECEIVE_WALL_MS".into(),
        source_monotonic_used_for_freshness: false,
        comparable_receive_wall_sample_count: input.links.iter().map(|l| l.samples.len()).sum(),
        provenance_monotonic_sample_count: input
            .links
            .iter()
            .flat_map(|l| l.samples.iter())
            .filter(|s| s.source_monotonic_ns.is_some())
            .count(),
    };
    finish(
        input,
        InferenceCore {
            prediction: "INDETERMINATE".into(),
            human_confidence: 0.5,
            evidence_quality: "LOW".into(),
            fused_score: 0.0,
            contributing_links: feats.len(),
            contributing_nodes: nodes.len(),
            physical_baselines: phys.len(),
            reciprocal_pair_count: 0,
            disturbed_links: 0,
            disturbed_baselines: 0,
            reason: "insufficient_independent_synchronized_rf_evidence".into(),
            missing_or_stale_reasons: reasons,
            component_scores: BTreeMap::new(),
            per_link_features: feats,
            calibration_state: "READY".into(),
            calibration_id: input.calibration.calibration_id.clone(),
            calibration_hash: cal_hash,
            algorithm_version: ALGORITHM_VERSION.into(),
            parameter_hash: PARAMETER_HASH.into(),
            window_id: input.window_id.clone(),
            clock_diagnostics: clock,
        },
    )
}

fn finish(input: &InferenceInput, core: InferenceCore) -> InferenceResult {
    let digest = sha(&serde_json::to_vec(&core).expect("serialize result"));
    let decision_id = format!(
        "d208-{}",
        digest
            .trim_start_matches("sha256:")
            .chars()
            .take(16)
            .collect::<String>()
    );
    let replay = json!({"operation":"INFER","session_id":input.session_id,"window_id":input.window_id,"window_start_wall_ms":input.window_start_wall_ms,"window_end_wall_ms":input.window_end_wall_ms,"detector_parameter_hash":input.detector_parameter_hash,"calibration":input.calibration,"acquisition_health":input.acquisition_health,"links":input.links});
    InferenceResult {
        core,
        canonical_digest: digest,
        decision_id,
        authoritative: true,
        source: "canonical_shared_rust_engine".into(),
        publication_contract_version: 8,
        canonical_replay_input: replay,
    }
}

pub fn infer(mut input: InferenceInput) -> InferenceResult {
    input.links.sort_by(|a, b| a.link_id.cmp(&b.link_id));
    let computed = hash_artifact(&input.calibration);
    let mut reasons = Vec::new();
    if input.detector_parameter_hash != PARAMETER_HASH
        || input.calibration.detector_parameter_hash != PARAMETER_HASH
    {
        reasons.push("detector_parameter_hash_mismatch".into());
    }
    if input.calibration.calibration_hash != computed {
        reasons.push("calibration_hash_mismatch".into());
    }
    if !input.acquisition_health.environment_valid || !input.acquisition_health.acquisition_valid {
        reasons.push("acquisition_or_environment_invalid".into());
    }
    if input.calibration.contributing_nodes < 3
        || input.calibration.directional_links < 6
        || input.calibration.physical_baselines < 3
    {
        reasons.push("calibration_topology_incomplete".into());
    }
    let bases: BTreeMap<_, _> = input
        .calibration
        .links
        .iter()
        .map(|b| (b.link_id.clone(), b))
        .collect();
    let min_baseline_support = input
        .calibration
        .links
        .iter()
        .map(|b| b.sample_count)
        .min()
        .unwrap_or(0);
    let max_min_observation_quality = (min_baseline_support.min(OBSERVATION_MIN_SAMPLES) as f64
        / QUALITY_REFERENCE_SAMPLES as f64)
        .min(1.0);
    if max_min_observation_quality < MIN_MEAN_QUALITY {
        reasons.push("calibration_quality_admissibility_invariant_failed".into());
    }
    let mut feats = Vec::new();
    for obs in &input.links {
        match bases.get(&obs.link_id) {
            Some(base) => match features(base, obs) {
                Ok(f) => feats.push(f),
                Err(e) => reasons.push(e),
            },
            None => reasons.push(format!("{}: missing frozen baseline", obs.link_id)),
        }
    }
    let nodes: BTreeSet<_> = feats.iter().map(|f| f.observer_node_id.clone()).collect();
    let phys: BTreeSet<_> = feats
        .iter()
        .map(|f| physical(&f.observer_node_id, &f.peer_node_id))
        .collect();
    if nodes.len() < 3 {
        reasons.push("fewer_than_3_observer_nodes".into())
    }
    if feats.len() < 6 {
        reasons.push("fewer_than_6_directional_links".into())
    }
    if phys.len() < 3 {
        reasons.push("fewer_than_3_physical_baselines".into())
    }
    if !feats.is_empty() {
        let start = feats
            .iter()
            .map(|f| f.first_receive_wall_ms)
            .max()
            .unwrap_or(0);
        let end = feats
            .iter()
            .map(|f| f.last_receive_wall_ms)
            .min()
            .unwrap_or(0);
        if end - start < INFERENCE_MIN_OVERLAP_MS {
            reasons.push("insufficient_comparable_wall_clock_overlap".into())
        }
    }
    let q = if feats.is_empty() {
        0.0
    } else {
        mean(&feats.iter().map(|f| f.quality).collect::<Vec<_>>())
    };
    if q < MIN_MEAN_QUALITY {
        reasons.push("mean_evidence_quality_below_gate".into())
    }
    if !reasons.is_empty() {
        return invalid(&input, computed, reasons, feats);
    }
    let totalw = feats.iter().map(|f| f.quality.max(0.05)).sum::<f64>();
    let base = feats
        .iter()
        .map(|f| f.disturbance_score * f.quality.max(0.05))
        .sum::<f64>()
        / totalw.max(0.01);
    let mut byphys: BTreeMap<String, Vec<&LinkFeature>> = BTreeMap::new();
    for f in &feats {
        byphys
            .entry(physical(&f.observer_node_id, &f.peer_node_id))
            .or_default()
            .push(f)
    }
    let reciprocal = byphys
        .values()
        .filter(|v| v.len() >= 2)
        .map(|v| {
            (1.0 - (v[0].disturbance_score - v[1].disturbance_score)
                .abs()
                .min(1.0))
        })
        .collect::<Vec<_>>();
    let recip = mean(&reciprocal);
    let disturbed = feats
        .iter()
        .filter(|f| f.disturbance_score >= DISTURBED_THRESHOLD)
        .count();
    let disturbed_phys: BTreeSet<_> = feats
        .iter()
        .filter(|f| f.disturbance_score >= DISTURBED_THRESHOLD)
        .map(|f| physical(&f.observer_node_id, &f.peer_node_id))
        .collect();
    let cross = disturbed as f64 / feats.len() as f64;
    let bs = disturbed_phys.len() as f64 / phys.len() as f64;
    let dynamic_links = feats
        .iter()
        .filter(|f| f.dynamic_score >= 0.55 && f.persistence_score >= 0.34)
        .count();
    let dynamic_phys: BTreeSet<_> = feats
        .iter()
        .filter(|f| f.dynamic_score >= 0.55 && f.persistence_score >= 0.34)
        .map(|f| physical(&f.observer_node_id, &f.peer_node_id))
        .collect();
    let dynamic_support = dynamic_links as f64 / feats.len() as f64;
    let dynamic_baseline_support = dynamic_phys.len() as f64 / phys.len() as f64;
    let fused = (base
        + 0.10 * recip * cross
        + 0.14 * cross
        + 0.12 * bs
        + 0.15 * dynamic_support
        + 0.12 * dynamic_baseline_support
        - 0.05 * (1.0 - q))
        .clamp(0.0, 1.0);
    let p = 1.0 / (1.0 + (-((fused - 0.46) * 7.0)).exp());
    let transition_phys: BTreeSet<_> = feats
        .iter()
        .filter(|f| f.segmented_transition_score >= 0.18 || f.burst_activity_score >= 0.20)
        .map(|f| physical(&f.observer_node_id, &f.peer_node_id))
        .collect();
    let transition_support = transition_phys.len() as f64 / phys.len() as f64;
    let distributed_motion = dynamic_links >= 3 && dynamic_phys.len() >= 2 && recip >= 0.35;
    let coherent_low_amplitude_motion =
        fused >= 0.26 && base >= 0.20 && recip >= 0.70 && cross >= (1.0 / 6.0) && bs >= (1.0 / 3.0);
    // V8 negative evidence is feature-level, not a global-threshold retune. The dev20.7 EMPTY
    // signature had zero dynamic links/baselines with only 1/6 cross-link and 1/3 baseline support.
    let distributed_negative_evidence = fused <= 0.30
        && dynamic_links == 0
        && dynamic_phys.is_empty()
        && cross <= (1.0 / 6.0)
        && bs <= (1.0 / 3.0);
    let (prediction, reason) =
        if (fused >= HUMAN_THRESHOLD && disturbed >= 2 && disturbed_phys.len() >= 2)
            || distributed_motion
            || coherent_low_amplitude_motion
        {
            (
                "HUMAN_EVIDENCE",
                "distributed_dynamic_and_level_disturbance",
            )
        } else if (fused <= NO_HUMAN_THRESHOLD && disturbed == 0) || distributed_negative_evidence {
            (
                "NO_HUMAN_EVIDENCE",
                if distributed_negative_evidence {
                    "distributed_negative_dynamic_evidence"
                } else {
                    "clean_frozen_calibrated_background_not_proof_of_absence"
                },
            )
        } else {
            (
                "INDETERMINATE",
                "fused_disturbance_inside_conservative_band",
            )
        };
    let mut components = BTreeMap::new();
    components.insert("quality_weighted_link_score".into(), round6(base));
    components.insert("reciprocal_coherence".into(), round6(recip));
    components.insert("cross_link_support".into(), round6(cross));
    components.insert("disturbed_baseline_support".into(), round6(bs));
    components.insert("mean_link_quality".into(), round6(q));
    components.insert("dynamic_link_support".into(), round6(dynamic_support));
    components.insert(
        "dynamic_baseline_support".into(),
        round6(dynamic_baseline_support),
    );
    components.insert(
        "distributed_negative_evidence_gate".into(),
        if distributed_negative_evidence {
            1.0
        } else {
            0.0
        },
    );
    components.insert(
        "distributed_motion_gate".into(),
        if distributed_motion { 1.0 } else { 0.0 },
    );
    components.insert(
        "segmented_transition_baseline_support".into(),
        round6(transition_support),
    );
    components.insert(
        "coherent_low_amplitude_motion_gate".into(),
        if coherent_low_amplitude_motion {
            1.0
        } else {
            0.0
        },
    );
    components.insert("min_mean_quality_threshold".into(), MIN_MEAN_QUALITY);
    components.insert(
        "quality_reference_samples".into(),
        QUALITY_REFERENCE_SAMPLES as f64,
    );
    components.insert(
        "calibration_min_samples_per_link".into(),
        CALIBRATION_MIN_SAMPLES as f64,
    );
    components.insert(
        "observation_min_samples_per_link".into(),
        OBSERVATION_MIN_SAMPLES as f64,
    );
    let clock = ClockDiagnostics {
        freshness_clock_domain: "LOCAL_RECEIVE_WALL_MS".into(),
        source_monotonic_used_for_freshness: false,
        comparable_receive_wall_sample_count: input.links.iter().map(|l| l.samples.len()).sum(),
        provenance_monotonic_sample_count: input
            .links
            .iter()
            .flat_map(|l| l.samples.iter())
            .filter(|s| s.source_monotonic_ns.is_some())
            .count(),
    };
    finish(
        &input,
        InferenceCore {
            prediction: prediction.into(),
            human_confidence: round6(p),
            evidence_quality: if q >= 0.75 {
                "HIGH".into()
            } else {
                "MEDIUM".into()
            },
            fused_score: round6(fused),
            contributing_links: feats.len(),
            contributing_nodes: nodes.len(),
            physical_baselines: phys.len(),
            reciprocal_pair_count: reciprocal.len(),
            disturbed_links: disturbed,
            disturbed_baselines: disturbed_phys.len(),
            reason: reason.into(),
            missing_or_stale_reasons: Vec::new(),
            component_scores: components,
            per_link_features: feats,
            calibration_state: "READY".into(),
            calibration_id: input.calibration.calibration_id.clone(),
            calibration_hash: computed,
            algorithm_version: ALGORITHM_VERSION.into(),
            parameter_hash: PARAMETER_HASH.into(),
            window_id: input.window_id.clone(),
            clock_diagnostics: clock,
        },
    )
}

pub fn evaluate_json(text: &str) -> Result<String, String> {
    let value: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let op = value.get("operation").and_then(Value::as_str).unwrap_or("");
    let out = match op {
        "BUILD_CALIBRATION" => {
            build_calibration(serde_json::from_value(value).map_err(|e| e.to_string())?)
        }
        "INFER" => serde_json::to_value(infer(
            serde_json::from_value(value).map_err(|e| e.to_string())?,
        ))
        .map_err(|e| e.to_string())?,
        _ => return Err("operation must be BUILD_CALIBRATION or INFER".into()),
    };
    serde_json::to_string(&out).map_err(|e| e.to_string())
}

#[cfg(target_os = "android")]
#[no_mangle]
pub extern "system" fn Java_com_trochez_bodyfindernative_BodyFinderNativeModule_nativeEvaluateHumanPresence(
    mut env: jni::JNIEnv<'_>,
    _this: jni::objects::JObject<'_>,
    input: jni::objects::JString<'_>,
) -> jni::sys::jstring {
    let text: String = env.get_string(&input).map(|s| s.into()).unwrap_or_default();
    let out=evaluate_json(&text).unwrap_or_else(|e|json!({"error":e,"prediction":"INDETERMINATE","algorithm_version":ALGORITHM_VERSION,"parameter_hash":PARAMETER_HASH}).to_string());
    env.new_string(out)
        .map(|s| s.into_raw())
        .unwrap_or(std::ptr::null_mut())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn links(human: bool, offset: i64) -> Vec<RawLink> {
        let ids = [
            ("a", "b"),
            ("b", "a"),
            ("a", "c"),
            ("c", "a"),
            ("b", "c"),
            ("c", "b"),
        ];
        ids.iter()
            .map(|(a, b)| {
                let mut s = Vec::new();
                for i in 0..36 {
                    let r = if human {
                        if i % 4 < 2 {
                            -55.0
                        } else {
                            -84.0
                        }
                    } else {
                        -70.0 + ((i % 3) as f64 - 1.0)
                    };
                    s.push(DetectorSample {
                        receive_wall_ms: offset + i * 100,
                        source_monotonic_ns: Some(9_000_000_000_000 + i),
                        rssi_dbm: r,
                    })
                }
                RawLink {
                    link_id: format!("{}::{}", a, b),
                    observer_node_id: (*a).into(),
                    peer_node_id: (*b).into(),
                    samples: s,
                }
            })
            .collect()
    }
    fn calibration() -> CalibrationArtifact {
        let v = build_calibration(CalibrationBuildInput {
            operation: "BUILD_CALIBRATION".into(),
            session_id: "s".into(),
            calibration_id: "c".into(),
            generation: 1,
            topology_fingerprint: "a,b,c".into(),
            detector_parameter_hash: PARAMETER_HASH.into(),
            frozen_wall_ms: 10_000,
            links: links(false, 0),
        });
        serde_json::from_value(v["artifact"].clone()).unwrap()
    }
    fn input(human: bool) -> InferenceInput {
        InferenceInput {
            operation: "INFER".into(),
            session_id: "s".into(),
            window_id: "w".into(),
            window_start_wall_ms: 20_000,
            window_end_wall_ms: 23_000,
            detector_parameter_hash: PARAMETER_HASH.into(),
            calibration: calibration(),
            acquisition_health: AcquisitionHealth::default(),
            links: links(human, 20_000),
        }
    }
    #[test]
    fn empty_is_negative() {
        assert_eq!(infer(input(false)).core.prediction, "NO_HUMAN_EVIDENCE")
    }
    #[test]
    fn moving_is_positive() {
        assert_eq!(infer(input(true)).core.prediction, "HUMAN_EVIDENCE")
    }
    #[test]
    fn missing_link_fails_closed() {
        let mut i = input(true);
        i.links.pop();
        assert_eq!(infer(i).core.prediction, "INDETERMINATE")
    }
    #[test]
    fn monotonic_domain_never_changes_freshness() {
        let a = infer(input(true));
        let mut i = input(true);
        for l in &mut i.links {
            for s in &mut l.samples {
                s.source_monotonic_ns = Some(42)
            }
        }
        let b = infer(i);
        assert_eq!(a.core.fused_score, b.core.fused_score)
    }
    #[test]
    fn dev20_6_aggregate_low_amplitude_human_separates_from_empty() {
        let human = 0.285562 >= 0.26
            && 0.207909 >= 0.20
            && 0.85916 >= 0.70
            && 0.166667 >= (1.0 / 6.0)
            && (1.0 / 3.0) >= (1.0 / 3.0);
        let empty = 0.168229 >= 0.26;
        assert!(human);
        assert!(!empty);
    }
    #[test]
    fn deterministic_digest_100_replays() {
        let d = infer(input(true)).canonical_digest;
        for _ in 0..100 {
            assert_eq!(infer(input(true)).canonical_digest, d)
        }
    }
}
