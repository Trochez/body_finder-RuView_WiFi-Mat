pub mod human_detector;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use std::io::BufRead;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CapabilityTruth {
    pub state: String,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidencePolicy {
    pub screenshots_required: bool,
    pub json_self_contained: bool,
    pub simulation_is_physical_proof: bool,
}

impl Default for EvidencePolicy {
    fn default() -> Self {
        Self {
            screenshots_required: false,
            json_self_contained: true,
            simulation_is_physical_proof: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SessionManifest {
    pub schema_version: u16,
    pub session_id: String,
    pub node_id: String,
    pub platform: String,
    pub software_build: String,
    pub started_unix_ms: u128,
    pub ended_unix_ms: Option<u128>,
    pub monotonic_origin: String,
    pub sample_interval_ms: u64,
    pub capabilities: BTreeMap<String, CapabilityTruth>,
    #[serde(default)]
    pub device_inventory: Vec<serde_json::Value>,
    #[serde(default)]
    pub evidence_policy: EvidencePolicy,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RFMeasurement {
    pub schema_version: u16,
    pub timestamp_monotonic_ns: u64,
    pub timestamp_unix_ms: Option<u128>,
    pub source_node_id: String,
    pub peer_or_bssid: String,
    pub modality: String,
    pub raw_value: f64,
    pub variance: f64,
    pub quality: String,
    pub position: Option<serde_json::Value>,
    pub orientation: Option<serde_json::Value>,
    pub frequency_mhz: Option<f64>,
    pub channel: Option<u32>,
    pub capability_provenance: String,
    pub session_id: String,
    #[serde(default)]
    pub metadata: BTreeMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CalibrationStats {
    pub count: usize,
    pub mean: f64,
    pub median: f64,
    pub variance: f64,
    pub std_dev: f64,
    pub mad: f64,
}

impl CalibrationStats {
    pub fn from_values(values: &[f64]) -> Option<Self> {
        if values.is_empty() || values.iter().any(|v| !v.is_finite()) {
            return None;
        }
        let count = values.len();
        let mean = values.iter().sum::<f64>() / count as f64;
        let variance = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / count as f64;
        let mut sorted = values.to_vec();
        sorted.sort_by(|a, b| a.total_cmp(b));
        let median = if count % 2 == 0 {
            (sorted[count / 2 - 1] + sorted[count / 2]) / 2.0
        } else {
            sorted[count / 2]
        };
        let mut deviations: Vec<f64> = values.iter().map(|v| (v - median).abs()).collect();
        deviations.sort_by(|a, b| a.total_cmp(b));
        let mad = if count % 2 == 0 {
            (deviations[count / 2 - 1] + deviations[count / 2]) / 2.0
        } else {
            deviations[count / 2]
        };
        Some(Self {
            count,
            mean,
            median,
            variance,
            std_dev: variance.sqrt(),
            mad,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LinkFeatureVector {
    pub link_id: String,
    pub sample_count: usize,
    pub delta_from_baseline: f64,
    pub rolling_variance: f64,
    pub mad: f64,
    pub change_point_score: f64,
    pub autocorrelation_lag1: f64,
    pub packet_loss_delta: f64,
    pub spectral_energy_proxy: f64,
    pub quality: f64,
}

pub fn validate_measurements(
    manifest: &SessionManifest,
    measurements: &[RFMeasurement],
) -> Result<()> {
    if manifest.schema_version != 1 {
        bail!("unsupported manifest schema {}", manifest.schema_version);
    }
    if manifest.evidence_policy.screenshots_required
        || !manifest.evidence_policy.json_self_contained
        || manifest.evidence_policy.simulation_is_physical_proof
    {
        bail!("invalid evidence policy");
    }
    if measurements.is_empty() {
        bail!("session contains no RF measurements");
    }
    let mut last: HashMap<(String, String, String), u64> = HashMap::new();
    for (i, m) in measurements.iter().enumerate() {
        if m.schema_version != 1 {
            bail!("measurement {i}: unsupported schema");
        }
        if m.session_id != manifest.session_id {
            bail!("measurement {i}: session mismatch");
        }
        if m.source_node_id.is_empty()
            || m.peer_or_bssid.is_empty()
            || m.capability_provenance.is_empty()
        {
            bail!("measurement {i}: missing identity/provenance");
        }
        if !m.raw_value.is_finite() || !m.variance.is_finite() || m.variance < 0.0 {
            bail!("measurement {i}: invalid numeric value");
        }
        let key = (
            m.source_node_id.clone(),
            m.peer_or_bssid.clone(),
            m.modality.clone(),
        );
        if let Some(prev) = last.insert(key, m.timestamp_monotonic_ns) {
            if m.timestamp_monotonic_ns < prev {
                bail!("measurement {i}: non-monotonic timestamp");
            }
        }
    }
    Ok(())
}

pub fn read_measurements<R: BufRead>(reader: R) -> Result<Vec<RFMeasurement>> {
    let mut out = Vec::new();
    for (index, line) in reader.lines().enumerate() {
        let line = line.with_context(|| format!("read line {}", index + 1))?;
        if line.trim().is_empty() {
            continue;
        }
        out.push(
            serde_json::from_str(&line)
                .with_context(|| format!("parse RFMeasurement line {}", index + 1))?,
        );
    }
    Ok(out)
}

pub fn canonical_measurements(mut measurements: Vec<RFMeasurement>) -> Vec<RFMeasurement> {
    measurements.sort_by(|a, b| {
        (
            a.timestamp_monotonic_ns,
            &a.source_node_id,
            &a.peer_or_bssid,
            &a.modality,
        )
            .cmp(&(
                b.timestamp_monotonic_ns,
                &b.source_node_id,
                &b.peer_or_bssid,
                &b.modality,
            ))
    });
    measurements
}

pub fn deterministic_digest(measurements: &[RFMeasurement]) -> Result<String> {
    let canonical = canonical_measurements(measurements.to_vec());
    let mut hash: u64 = 0xcbf29ce484222325;
    for m in canonical {
        let mut bytes = serde_json::to_vec(&m)?;
        bytes.push(b'\n');
        for byte in bytes {
            hash ^= byte as u64;
            hash = hash.wrapping_mul(0x100000001b3);
        }
    }
    Ok(format!("fnv1a64:{hash:016x}"))
}

pub fn extract_features(
    measurements: &[RFMeasurement],
    baseline: &CalibrationStats,
) -> Option<LinkFeatureVector> {
    if measurements.len() < 2 {
        return None;
    }
    let values: Vec<f64> = measurements.iter().map(|m| m.raw_value).collect();
    let stats = CalibrationStats::from_values(&values)?;
    let delta = stats.mean - baseline.mean;
    let sigma = baseline.std_dev.max(1.0);
    let change = (delta.abs() / sigma).min(20.0);
    let mut numerator = 0.0;
    let mut denom = 0.0;
    for pair in values.windows(2) {
        numerator += (pair[0] - stats.mean) * (pair[1] - stats.mean);
        denom += (pair[0] - stats.mean).powi(2);
    }
    let autocorrelation = if denom > 1e-12 {
        numerator / denom
    } else {
        0.0
    };
    let spectral_proxy = values
        .windows(2)
        .map(|p| (p[1] - p[0]).powi(2))
        .sum::<f64>()
        / (values.len() - 1) as f64;
    let first = &measurements[0];
    Some(LinkFeatureVector {
        link_id: format!(
            "{}::{}::{}",
            first.source_node_id, first.peer_or_bssid, first.modality
        ),
        sample_count: values.len(),
        delta_from_baseline: delta,
        rolling_variance: stats.variance,
        mad: stats.mad,
        change_point_score: change,
        autocorrelation_lag1: autocorrelation,
        packet_loss_delta: 0.0,
        spectral_energy_proxy: spectral_proxy,
        quality: (values.len() as f64 / 20.0).min(1.0),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sample(ts: u64, v: f64) -> RFMeasurement {
        RFMeasurement {
            schema_version: 1,
            timestamp_monotonic_ns: ts,
            timestamp_unix_ms: None,
            source_node_id: "n1".into(),
            peer_or_bssid: "aa:bb".into(),
            modality: "WIFI_CONNECTED_RSSI_DBM".into(),
            raw_value: v,
            variance: 1.0,
            quality: "MEDIUM".into(),
            position: None,
            orientation: None,
            frequency_mhz: Some(5180.0),
            channel: Some(36),
            capability_provenance: "test-fixture-not-physical-proof".into(),
            session_id: "s1".into(),
            metadata: BTreeMap::new(),
        }
    }
    fn manifest() -> SessionManifest {
        SessionManifest {
            schema_version: 1,
            session_id: "s1".into(),
            node_id: "n1".into(),
            platform: "fixture".into(),
            software_build: "test".into(),
            started_unix_ms: 0,
            ended_unix_ms: Some(1),
            monotonic_origin: "PROCESS_START".into(),
            sample_interval_ms: 500,
            capabilities: BTreeMap::new(),
            device_inventory: vec![],
            evidence_policy: EvidencePolicy::default(),
        }
    }
    #[test]
    fn round_trip_and_determinism() {
        let xs = vec![sample(1, -50.0), sample(2, -48.0)];
        validate_measurements(&manifest(), &xs).unwrap();
        let a = deterministic_digest(&xs).unwrap();
        let b = deterministic_digest(&xs).unwrap();
        assert_eq!(a, b);
        let json = serde_json::to_string(&xs[0]).unwrap();
        assert_eq!(serde_json::from_str::<RFMeasurement>(&json).unwrap(), xs[0]);
    }
    #[test]
    fn rejects_time_reversal() {
        let xs = vec![sample(2, -50.0), sample(1, -48.0)];
        assert!(validate_measurements(&manifest(), &xs).is_err());
    }
    #[test]
    fn calibration_and_features() {
        let b = CalibrationStats::from_values(&[-60.0, -61.0, -59.0, -60.0]).unwrap();
        let xs = vec![sample(1, -52.0), sample(2, -50.0), sample(3, -51.0)];
        let f = extract_features(&xs, &b).unwrap();
        assert!(f.change_point_score > 2.0);
        assert_eq!(f.sample_count, 3);
    }
}
