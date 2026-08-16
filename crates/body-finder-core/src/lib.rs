use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const PROTOCOL_VERSION: u16 = 1;
pub const FABRIC_PORT: u16 = 47_777;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CapabilityState {
    Working,
    WorkingDegraded,
    SupportedUnverified,
    Unsupported,
    PermissionRequired,
    ProbeFailed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CapabilityProbe {
    pub state: CapabilityState,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct NodePosition {
    pub x_m: f64,
    pub y_m: f64,
    #[serde(default)]
    pub z_m: f64,
    #[serde(default = "default_position_sigma")]
    pub sigma_m: f64,
}

fn default_position_sigma() -> f64 { 0.25 }

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NodeAdvertisement {
    pub protocol_version: u16,
    pub session_id: String,
    pub node_id: String,
    pub display_name: String,
    pub platform: String,
    pub monotonic_ns: u64,
    pub coordinator_score: f32,
    pub capabilities: BTreeMap<String, CapabilityProbe>,
    pub rssi_dbm: Option<f64>,
    pub baseline_rssi_dbm: Option<f64>,
    pub baseline_sigma_db: Option<f64>,
    pub position: Option<NodePosition>,
    #[serde(default)]
    pub scanning: bool,
}

impl NodeAdvertisement {
    pub fn anomaly_z(&self) -> Option<f64> {
        let current = self.rssi_dbm?;
        let baseline = self.baseline_rssi_dbm?;
        let sigma = self.baseline_sigma_db.unwrap_or(2.0).max(1.0);
        Some(((current - baseline).abs() / sigma).min(20.0))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidenceContribution {
    pub node_id: String,
    pub source: String,
    pub anomaly_z: f64,
    pub weight: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HumanEstimate {
    pub method: String,
    pub state: String,
    pub x_m: f64,
    pub y_m: f64,
    pub z_m: f64,
    pub range_m: f64,
    pub bearing_deg: f64,
    pub human_confidence: f64,
    pub uncertainty_percent: f64,
    pub error_radius_95_m: f64,
    pub evidence_quality: String,
    pub covariance_2x2: [[f64; 2]; 2],
    pub provenance: Vec<EvidenceContribution>,
}

/// Experimental commodity-device baseline.
///
/// This is intentionally conservative and inspectable. It does *not* claim CSI or
/// through-wall validation. It weights the known node positions by each node's
/// calibrated Wi-Fi RSSI disturbance. Physical ground-truth testing decides whether
/// this modality is useful in a specific environment.
pub fn estimate_from_rssi(nodes: &[NodeAdvertisement]) -> Option<HumanEstimate> {
    let mut usable = Vec::new();
    for n in nodes {
        if !n.scanning { continue; }
        let p = n.position.as_ref()?;
        let z = n.anomaly_z()?;
        if z >= 0.75 {
            usable.push((n, p, z));
        }
    }
    if usable.len() < 3 { return None; }

    let sum_w: f64 = usable.iter().map(|(_, _, z)| (z - 0.5).max(0.1)).sum();
    if sum_w <= 0.0 { return None; }

    let x = usable.iter().map(|(_, p, z)| p.x_m * (z - 0.5).max(0.1)).sum::<f64>() / sum_w;
    let y = usable.iter().map(|(_, p, z)| p.y_m * (z - 0.5).max(0.1)).sum::<f64>() / sum_w;

    let var_x = usable.iter().map(|(_, p, z)| {
        let w = (z - 0.5).max(0.1);
        w * ((p.x_m - x).powi(2) + p.sigma_m.powi(2))
    }).sum::<f64>() / sum_w;
    let var_y = usable.iter().map(|(_, p, z)| {
        let w = (z - 0.5).max(0.1);
        w * ((p.y_m - y).powi(2) + p.sigma_m.powi(2))
    }).sum::<f64>() / sum_w;

    // Inflate because commodity RSSI is strongly affected by multipath.
    let sigma_radial = (var_x + var_y).sqrt().max(0.5);
    let error95 = (2.4477 * sigma_radial).max(1.0);
    let range = (x * x + y * y).sqrt();
    let reference = range.max(2.0);
    let uncertainty = (100.0 * error95 / reference).clamp(0.0, 100.0);
    let mean_z = usable.iter().map(|(_, _, z)| *z).sum::<f64>() / usable.len() as f64;
    let confidence = (1.0 - (-0.35 * (mean_z - 0.75).max(0.0)).exp()).clamp(0.0, 0.95);

    let state = if mean_z >= 5.0 { "PROBABLE_HUMAN" } else { "POSSIBLE_HUMAN" };
    let quality = if uncertainty <= 20.0 { "HIGH" } else if uncertainty <= 40.0 { "MEDIUM" } else if uncertainty <= 70.0 { "LOW" } else { "VERY_LOW" };

    Some(HumanEstimate {
        method: "EXPERIMENTAL_RSSI_DISTURBANCE_CENTROID_V1".into(),
        state: state.into(),
        x_m: x,
        y_m: y,
        z_m: 0.0,
        range_m: range,
        bearing_deg: x.atan2(y).to_degrees(),
        human_confidence: confidence,
        uncertainty_percent: uncertainty,
        error_radius_95_m: error95,
        evidence_quality: quality.into(),
        covariance_2x2: [[var_x, 0.0], [0.0, var_y]],
        provenance: usable.into_iter().map(|(n, _, z)| EvidenceContribution {
            node_id: n.node_id.clone(),
            source: "WIFI_RSSI".into(),
            anomaly_z: z,
            weight: (z - 0.5).max(0.1) / sum_w,
        }).collect(),
    })
}

pub fn elect_coordinator(nodes: &[NodeAdvertisement]) -> Option<String> {
    nodes.iter().max_by(|a, b| {
        a.coordinator_score.partial_cmp(&b.coordinator_score).unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| b.node_id.cmp(&a.node_id))
    }).map(|n| n.node_id.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn node(id: &str, x: f64, y: f64, rssi: f64, baseline: f64) -> NodeAdvertisement {
        NodeAdvertisement {
            protocol_version: PROTOCOL_VERSION,
            session_id: "test".into(),
            node_id: id.into(),
            display_name: id.into(),
            platform: "test".into(),
            monotonic_ns: 1,
            coordinator_score: 0.5,
            capabilities: BTreeMap::new(),
            rssi_dbm: Some(rssi),
            baseline_rssi_dbm: Some(baseline),
            baseline_sigma_db: Some(1.0),
            position: Some(NodePosition { x_m: x, y_m: y, z_m: 0.0, sigma_m: 0.1 }),
            scanning: true,
        }
    }

    #[test]
    fn needs_three_positioned_calibrated_nodes() {
        assert!(estimate_from_rssi(&[node("a", 0.0, 0.0, -60.0, -50.0), node("b", 1.0, 0.0, -60.0, -50.0)]).is_none());
    }

    #[test]
    fn estimate_has_explicit_uncertainty_and_provenance() {
        let e = estimate_from_rssi(&[
            node("a", -2.0, 0.0, -60.0, -50.0),
            node("b", 2.0, 0.0, -58.0, -50.0),
            node("c", 0.0, 3.0, -56.0, -50.0),
        ]).unwrap();
        assert!(e.error_radius_95_m >= 1.0);
        assert!((0.0..=100.0).contains(&e.uncertainty_percent));
        assert_eq!(e.provenance.len(), 3);
        assert!(e.method.starts_with("EXPERIMENTAL_"));
    }

    #[test]
    fn protocol_round_trip() {
        let n = node("a", 0.0, 0.0, -55.0, -50.0);
        let s = serde_json::to_string(&n).unwrap();
        let decoded: NodeAdvertisement = serde_json::from_str(&s).unwrap();
        assert_eq!(decoded, n);
    }
}
