use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};

pub const PROTOCOL_VERSION: u16 = 2;
pub const FABRIC_PORT: u16 = 47_777;
pub const RANGE_SAMPLE_STALE_NS: u64 = 8_000_000_000;
pub const RANGE_REORDER_TOLERANCE_NS: u64 = 250_000_000;

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

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum RangingTechnology {
    AndroidRangingUwb,
    AndroidRangingBleCs,
    AndroidRangingWifiNanRtt,
    AndroidRangingBleRssi,
    WifiRttAware,
    WifiRttAccessPoint,
    AndroidxUwb,
    BleRssi,
    LinuxAdapter,
    WindowsAdapter,
    Unknown,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MeasurementQuality {
    High,
    Medium,
    Low,
    Rejected,
}

impl Default for MeasurementQuality {
    fn default() -> Self {
        Self::Low
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PairwiseRangeObservation {
    pub session_id: String,
    pub observer_node_id: String,
    pub peer_node_id: String,
    pub technology: RangingTechnology,
    pub monotonic_ns: u64,
    pub distance_m: Option<f64>,
    pub distance_sigma_m: Option<f64>,
    pub azimuth_deg: Option<f64>,
    pub azimuth_sigma_deg: Option<f64>,
    pub elevation_deg: Option<f64>,
    pub elevation_sigma_deg: Option<f64>,
    pub rssi_dbm: Option<f64>,
    #[serde(default)]
    pub quality: MeasurementQuality,
    pub source_detail: String,
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

fn default_position_sigma() -> f64 {
    1.0
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum GeometryState {
    DiscoveringNodes,
    Ranging,
    GeometryInsufficient,
    Geometry1d,
    Geometry2d,
    GeometryDegraded,
    GeometryStale,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub enum GeometryDimension {
    #[serde(rename = "UNKNOWN")]
    Unknown,
    #[serde(rename = "1D")]
    OneD,
    #[serde(rename = "2D")]
    TwoD,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NodePositionEstimate {
    pub node_id: String,
    pub x_m: f64,
    pub y_m: f64,
    pub z_m: f64,
    pub covariance_2x2: [[f64; 2]; 2],
    pub error_radius_95_m: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RejectedEdge {
    pub edge_id: String,
    pub reason: String,
    pub residual_m: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GeometrySolution {
    pub frame_id: String,
    pub revision: u64,
    pub generated_monotonic_ns: u64,
    pub dimension: GeometryDimension,
    pub state: GeometryState,
    pub anchor_node_id: String,
    pub axis_node_id: Option<String>,
    pub positions: Vec<NodePositionEstimate>,
    pub residual_rms_m: Option<f64>,
    pub condition_score: Option<f64>,
    pub used_edges: Vec<String>,
    pub rejected_edges: Vec<RejectedEdge>,
    pub reason: Option<String>,
}

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
    /// Legacy/debug-only. Production automatic geometry never consumes this field.
    #[serde(default)]
    pub position: Option<NodePosition>,
    #[serde(default)]
    pub scanning: bool,
    #[serde(default)]
    pub ble_identity: Option<String>,
    #[serde(default)]
    pub ranges: Vec<PairwiseRangeObservation>,
    #[serde(default)]
    pub manual_geometry_override: bool,
    /// The elected coordinator may publish the exact geometry revision it is using.
    /// This is derived output only and never feeds the geometry solver as an input.
    #[serde(default)]
    pub published_geometry: Option<GeometrySolution>,
    #[serde(default)]
    pub geometry_publisher_node_id: Option<String>,
}

impl NodeAdvertisement {
    pub fn anomaly_z(&self) -> Option<f64> {
        let current = self.rssi_dbm?;
        let baseline = self.baseline_rssi_dbm?;
        let sigma = self.baseline_sigma_db.unwrap_or(2.0).max(1.0);
        Some(((current - baseline).abs() / sigma).min(20.0))
    }
}

#[derive(Debug, Clone)]
struct Edge {
    id: String,
    a: String,
    b: String,
    technology: RangingTechnology,
    distance: f64,
    sigma: f64,
    quality_weight: f64,
    latest_observation_ns: u64,
}

fn quality_weight(quality: &MeasurementQuality) -> f64 {
    match quality {
        MeasurementQuality::High => 1.0,
        MeasurementQuality::Medium => 0.55,
        MeasurementQuality::Low => 0.18,
        MeasurementQuality::Rejected => 0.0,
    }
}

fn median(mut values: Vec<f64>) -> f64 {
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = values.len();
    if n % 2 == 0 {
        (values[n / 2 - 1] + values[n / 2]) / 2.0
    } else {
        values[n / 2]
    }
}

fn canonical_pair(a: &str, b: &str) -> (String, String) {
    if a <= b {
        (a.into(), b.into())
    } else {
        (b.into(), a.into())
    }
}

fn preferred_session(nodes: &[NodeAdvertisement]) -> Option<String> {
    let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
    for node in nodes.iter().filter(|n| n.protocol_version == PROTOCOL_VERSION) {
        *counts.entry(node.session_id.as_str()).or_default() += 1;
    }
    let mut best: Option<(&str, usize)> = None;
    for (session, count) in counts {
        match best {
            None => best = Some((session, count)),
            Some((best_session, best_count))
                if count > best_count || (count == best_count && session < best_session) =>
            {
                best = Some((session, count));
            }
            _ => {}
        }
    }
    best.map(|(session, _)| session.to_string())
}

fn active_nodes<'a>(
    nodes: &'a [NodeAdvertisement],
    rejected: &mut Vec<RejectedEdge>,
) -> Vec<&'a NodeAdvertisement> {
    let Some(session) = preferred_session(nodes) else {
        return Vec::new();
    };
    let mut active = Vec::new();
    for node in nodes {
        if node.protocol_version != PROTOCOL_VERSION {
            rejected.push(RejectedEdge {
                edge_id: format!("node::{}", node.node_id),
                reason: format!(
                    "protocol mismatch: got {}, expected {}",
                    node.protocol_version, PROTOCOL_VERSION
                ),
                residual_m: None,
            });
            continue;
        }
        if node.session_id != session {
            rejected.push(RejectedEdge {
                edge_id: format!("node::{}", node.node_id),
                reason: "cross-session node advertisement rejected".into(),
                residual_m: None,
            });
            continue;
        }
        active.push(node);
    }
    active
}

fn collect_edges(
    nodes: &[&NodeAdvertisement],
    rejected: &mut Vec<RejectedEdge>,
) -> Vec<Edge> {
    let node_ids: BTreeSet<&str> = nodes.iter().map(|n| n.node_id.as_str()).collect();
    let session = nodes.first().map(|n| n.session_id.as_str()).unwrap_or_default();

    let mut latest_by_source: BTreeMap<(String, String, RangingTechnology), u64> = BTreeMap::new();
    for node in nodes {
        for obs in &node.ranges {
            if obs.session_id == session && obs.observer_node_id == node.node_id {
                let key = (
                    obs.observer_node_id.clone(),
                    obs.peer_node_id.clone(),
                    obs.technology,
                );
                latest_by_source
                    .entry(key)
                    .and_modify(|latest| *latest = (*latest).max(obs.monotonic_ns))
                    .or_insert(obs.monotonic_ns);
            }
        }
    }

    let mut grouped: BTreeMap<
        (String, String, RangingTechnology),
        Vec<&PairwiseRangeObservation>,
    > = BTreeMap::new();

    for node in nodes {
        for obs in &node.ranges {
            let pair = canonical_pair(&obs.observer_node_id, &obs.peer_node_id);
            let edge_id = format!("{}::{}::{:?}", pair.0, pair.1, obs.technology);

            if obs.session_id != session
                || obs.session_id != node.session_id
                || obs.observer_node_id != node.node_id
            {
                rejected.push(RejectedEdge {
                    edge_id,
                    reason: "session/observer identity mismatch".into(),
                    residual_m: None,
                });
                continue;
            }
            if !node_ids.contains(obs.peer_node_id.as_str())
                || obs.peer_node_id == obs.observer_node_id
            {
                rejected.push(RejectedEdge {
                    edge_id,
                    reason: "peer not active in geometry graph".into(),
                    residual_m: None,
                });
                continue;
            }
            if obs.monotonic_ns
                > node
                    .monotonic_ns
                    .saturating_add(RANGE_REORDER_TOLERANCE_NS)
            {
                rejected.push(RejectedEdge {
                    edge_id,
                    reason: "range sample timestamp is implausibly ahead of its observer".into(),
                    residual_m: None,
                });
                continue;
            }
            let age = node.monotonic_ns.saturating_sub(obs.monotonic_ns);
            if age > RANGE_SAMPLE_STALE_NS {
                rejected.push(RejectedEdge {
                    edge_id,
                    reason: "stale range sample expired from geometry graph".into(),
                    residual_m: None,
                });
                continue;
            }
            let source_key = (
                obs.observer_node_id.clone(),
                obs.peer_node_id.clone(),
                obs.technology,
            );
            if let Some(latest) = latest_by_source.get(&source_key) {
                if latest.saturating_sub(obs.monotonic_ns) > RANGE_REORDER_TOLERANCE_NS {
                    rejected.push(RejectedEdge {
                        edge_id,
                        reason: "replayed/out-of-order range sample rejected".into(),
                        residual_m: None,
                    });
                    continue;
                }
            }

            let Some(distance) = obs.distance_m else {
                continue;
            };
            let sigma = obs.distance_sigma_m.unwrap_or(3.0);
            if !distance.is_finite()
                || !(0.05..=100.0).contains(&distance)
                || !sigma.is_finite()
                || !(0.05..=30.0).contains(&sigma)
                || quality_weight(&obs.quality) <= 0.0
            {
                rejected.push(RejectedEdge {
                    edge_id,
                    reason: "invalid or rejected range sample".into(),
                    residual_m: None,
                });
                continue;
            }
            grouped
                .entry((pair.0, pair.1, obs.technology))
                .or_default()
                .push(obs);
        }
    }

    // Aggregate reciprocal observations once per pair+technology. Then select the
    // strongest source for each pair instead of averaging UWB/RTT and BLE-RSSI
    // as if they had equivalent error models.
    let mut best_by_pair: BTreeMap<(String, String), Edge> = BTreeMap::new();
    for ((a, b, technology), samples) in grouped {
        let distances: Vec<f64> = samples.iter().filter_map(|o| o.distance_m).collect();
        if distances.is_empty() {
            continue;
        }
        let distance = median(distances.clone());
        let mad = median(distances.iter().map(|v| (v - distance).abs()).collect());
        let reported_sigma = median(
            samples
                .iter()
                .map(|o| o.distance_sigma_m.unwrap_or(3.0))
                .collect(),
        );
        let sigma = reported_sigma.max(1.4826 * mad).max(0.15);
        let q = samples
            .iter()
            .map(|o| quality_weight(&o.quality))
            .fold(0.0_f64, f64::max);
        let latest_observation_ns = samples
            .iter()
            .map(|o| o.monotonic_ns)
            .max()
            .unwrap_or_default();
        let candidate = Edge {
            id: format!("{}::{}::{:?}", a, b, technology),
            a: a.clone(),
            b: b.clone(),
            technology,
            distance,
            sigma,
            quality_weight: q,
            latest_observation_ns,
        };
        let candidate_score = candidate.quality_weight / candidate.sigma.powi(2).max(0.02);
        match best_by_pair.get(&(a.clone(), b.clone())) {
            Some(current) => {
                let current_score = current.quality_weight / current.sigma.powi(2).max(0.02);
                if candidate_score > current_score
                    || ((candidate_score - current_score).abs() < 1e-12
                        && candidate.technology < current.technology)
                {
                    best_by_pair.insert((a, b), candidate);
                }
            }
            None => {
                best_by_pair.insert((a, b), candidate);
            }
        }
    }
    best_by_pair.into_values().collect()
}

fn largest_component(node_ids: &[String], edges: &[Edge]) -> Vec<String> {
    let mut adjacency: HashMap<&str, Vec<&str>> = HashMap::new();
    for edge in edges {
        adjacency.entry(&edge.a).or_default().push(&edge.b);
        adjacency.entry(&edge.b).or_default().push(&edge.a);
    }
    let mut seen = BTreeSet::new();
    let mut best = Vec::new();
    for id in node_ids {
        if seen.contains(id.as_str()) {
            continue;
        }
        let mut queue = VecDeque::from([id.as_str()]);
        let mut component = Vec::new();
        seen.insert(id.as_str());
        while let Some(current) = queue.pop_front() {
            component.push(current.to_string());
            for next in adjacency.get(current).into_iter().flatten() {
                if seen.insert(*next) {
                    queue.push_back(next);
                }
            }
        }
        component.sort();
        if component.len() > best.len()
            || (component.len() == best.len() && component < best)
        {
            best = component;
        }
    }
    best
}

fn edge_lookup<'a>(edges: &'a [Edge], a: &str, b: &str) -> Option<&'a Edge> {
    let (x, y) = canonical_pair(a, b);
    edges.iter().find(|edge| edge.a == x && edge.b == y)
}

fn weighted_degree(id: &str, edges: &[Edge]) -> f64 {
    edges
        .iter()
        .filter(|edge| edge.a == id || edge.b == id)
        .map(|edge| edge.quality_weight / edge.sigma.powi(2).max(0.02))
        .sum()
}

fn best_anchor(component: &[String], edges: &[Edge]) -> String {
    component
        .iter()
        .cloned()
        .max_by(|a, b| {
            weighted_degree(a, edges)
                .partial_cmp(&weighted_degree(b, edges))
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| b.cmp(a))
        })
        .unwrap_or_default()
}

fn best_axis(anchor: &str, component: &[String], edges: &[Edge]) -> Option<String> {
    component
        .iter()
        .filter(|id| id.as_str() != anchor && edge_lookup(edges, anchor, id).is_some())
        .cloned()
        .max_by(|a, b| {
            let edge_a = edge_lookup(edges, anchor, a).expect("axis edge exists");
            let edge_b = edge_lookup(edges, anchor, b).expect("axis edge exists");
            let weight_a = edge_a.quality_weight / edge_a.sigma.powi(2).max(0.02);
            let weight_b = edge_b.quality_weight / edge_b.sigma.powi(2).max(0.02);
            weight_a
                .partial_cmp(&weight_b)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| b.cmp(a))
        })
}

fn initialize_positions(
    component: &[String],
    edges: &[Edge],
    anchor: &str,
    axis: &str,
) -> Option<(BTreeMap<String, (f64, f64)>, String)> {
    let d_ab = edge_lookup(edges, anchor, axis)?.distance;
    let mut positions = BTreeMap::new();
    positions.insert(anchor.into(), (0.0, 0.0));
    positions.insert(axis.into(), (d_ab, 0.0));

    let mut best_third: Option<(String, f64, f64, f64)> = None;
    for candidate in component
        .iter()
        .filter(|id| id.as_str() != anchor && id.as_str() != axis)
    {
        let Some(ac) = edge_lookup(edges, anchor, candidate) else {
            continue;
        };
        let Some(bc) = edge_lookup(edges, axis, candidate) else {
            continue;
        };
        let x = (ac.distance.powi(2) + d_ab.powi(2) - bc.distance.powi(2))
            / (2.0 * d_ab.max(1e-6));
        let y_squared = ac.distance.powi(2) - x.powi(2);
        if y_squared <= 0.0 {
            continue;
        }
        let y = y_squared.sqrt();
        let leverage = y / ac.distance.max(bc.distance).max(d_ab).max(0.1);
        if best_third
            .as_ref()
            .map(|value| leverage > value.3)
            .unwrap_or(true)
        {
            best_third = Some((candidate.clone(), x, y, leverage));
        }
    }

    let (third, x, y, leverage) = best_third?;
    if leverage < 0.06 {
        return None;
    }
    positions.insert(third.clone(), (x, y));

    loop {
        let mut added = false;
        for id in component {
            if positions.contains_key(id) {
                continue;
            }
            let neighbors: Vec<(String, &Edge)> = positions
                .keys()
                .filter_map(|known| edge_lookup(edges, id, known).map(|edge| (known.clone(), edge)))
                .collect();
            if neighbors.len() < 2 {
                continue;
            }
            let (first_id, first_edge) = &neighbors[0];
            let mut best: Option<(f64, f64, f64)> = None;
            for (second_id, second_edge) in neighbors.iter().skip(1) {
                let p1 = positions[first_id];
                let p2 = positions[second_id];
                let dx = p2.0 - p1.0;
                let dy = p2.1 - p1.1;
                let base = (dx * dx + dy * dy).sqrt();
                if base < 0.05 {
                    continue;
                }
                let along = (first_edge.distance.powi(2) + base.powi(2)
                    - second_edge.distance.powi(2))
                    / (2.0 * base);
                let height_squared = first_edge.distance.powi(2) - along.powi(2);
                if height_squared < 0.0 {
                    continue;
                }
                let height = height_squared.sqrt();
                let ux = dx / base;
                let uy = dy / base;
                for sign in [1.0_f64, -1.0_f64] {
                    let candidate_x = p1.0 + along * ux - sign * height * uy;
                    let candidate_y = p1.1 + along * uy + sign * height * ux;
                    let score = neighbors
                        .iter()
                        .map(|(known, edge)| {
                            let p = positions[known];
                            (((candidate_x - p.0).powi(2) + (candidate_y - p.1).powi(2))
                                .sqrt()
                                - edge.distance)
                                .abs()
                                / edge.sigma.max(0.15)
                        })
                        .sum::<f64>();
                    if best.as_ref().map(|value| score < value.2).unwrap_or(true) {
                        best = Some((candidate_x, candidate_y, score));
                    }
                }
            }
            if let Some((candidate_x, candidate_y, _)) = best {
                positions.insert(id.clone(), (candidate_x, candidate_y));
                added = true;
            }
        }
        if !added {
            break;
        }
    }
    Some((positions, third))
}

fn optimize_positions(
    positions: &mut BTreeMap<String, (f64, f64)>,
    edges: &[Edge],
    anchor: &str,
    axis: &str,
    third: &str,
) {
    for _ in 0..180 {
        let mut deltas: HashMap<String, (f64, f64, f64)> = HashMap::new();
        let mut max_step = 0.0_f64;
        for edge in edges {
            let (Some(a), Some(b)) = (
                positions.get(&edge.a).copied(),
                positions.get(&edge.b).copied(),
            ) else {
                continue;
            };
            let dx = b.0 - a.0;
            let dy = b.1 - a.1;
            let predicted = (dx * dx + dy * dy).sqrt().max(1e-6);
            let residual = predicted - edge.distance;
            // Huber-like clipping keeps a single bad edge from moving the whole frame.
            let robust = residual.clamp(
                -2.0 * edge.sigma.max(0.25),
                2.0 * edge.sigma.max(0.25),
            );
            let strength = (edge.quality_weight / edge.sigma.powi(2).max(0.04)).clamp(0.02, 20.0);
            let correction = robust * (0.20 * strength / (1.0 + strength));
            let ux = dx / predicted;
            let uy = dy / predicted;
            let a_fixed = edge.a == anchor || edge.a == axis;
            let b_fixed = edge.b == anchor || edge.b == axis;
            let share = if a_fixed || b_fixed { 1.0 } else { 0.5 };
            if !a_fixed {
                let value = deltas.entry(edge.a.clone()).or_insert((0.0, 0.0, 0.0));
                value.0 += correction * ux * share;
                value.1 += correction * uy * share;
                value.2 += 1.0;
            }
            if !b_fixed {
                let value = deltas.entry(edge.b.clone()).or_insert((0.0, 0.0, 0.0));
                value.0 -= correction * ux * share;
                value.1 -= correction * uy * share;
                value.2 += 1.0;
            }
        }
        for (id, (sum_x, sum_y, count)) in deltas {
            if count <= 0.0 {
                continue;
            }
            if let Some(position) = positions.get_mut(&id) {
                let dx = sum_x / count;
                let dy = sum_y / count;
                position.0 += dx;
                position.1 += dy;
                max_step = max_step.max((dx * dx + dy * dy).sqrt());
            }
        }
        if let Some(position) = positions.get_mut(third) {
            position.1 = position.1.abs();
        }
        if max_step < 1e-5 {
            break;
        }
    }
}

fn revision_hash(edges: &[Edge]) -> u64 {
    let mut hash = 0xcbf29ce484222325_u64;
    for edge in edges {
        let record = format!(
            "{}:{:.3}:{:.3}:{};",
            edge.id, edge.distance, edge.sigma, edge.latest_observation_ns
        );
        for byte in record.as_bytes() {
            hash ^= u64::from(*byte);
            hash = hash.wrapping_mul(0x100000001b3);
        }
    }
    hash
}

pub fn solve_geometry(nodes: &[NodeAdvertisement]) -> Option<GeometrySolution> {
    if nodes.is_empty() {
        return None;
    }

    let mut rejected = Vec::new();
    let active = active_nodes(nodes, &mut rejected);
    if active.is_empty() {
        return None;
    }
    let mut node_ids: Vec<String> = active.iter().map(|node| node.node_id.clone()).collect();
    node_ids.sort();
    node_ids.dedup();
    let generated = active
        .iter()
        .map(|node| node.monotonic_ns)
        .max()
        .unwrap_or_default();

    let all_edges = collect_edges(&active, &mut rejected);
    let component = largest_component(&node_ids, &all_edges);
    let component_set: BTreeSet<&str> = component.iter().map(String::as_str).collect();
    let mut edges: Vec<Edge> = all_edges
        .into_iter()
        .filter(|edge| {
            component_set.contains(edge.a.as_str()) && component_set.contains(edge.b.as_str())
        })
        .collect();
    edges.sort_by(|a, b| a.id.cmp(&b.id));
    let anchor = if component.is_empty() {
        node_ids[0].clone()
    } else {
        best_anchor(&component, &edges)
    };

    if component.len() < 2 || edges.is_empty() {
        let temporal_failure = rejected.iter().any(|item| {
            item.reason.contains("stale")
                || item.reason.contains("replayed")
                || item.reason.contains("timestamp")
        });
        return Some(GeometrySolution {
            frame_id: format!("bf2-{anchor}"),
            revision: revision_hash(&edges),
            generated_monotonic_ns: generated,
            dimension: GeometryDimension::Unknown,
            state: if temporal_failure {
                GeometryState::GeometryStale
            } else {
                GeometryState::GeometryInsufficient
            },
            anchor_node_id: anchor,
            axis_node_id: None,
            positions: vec![],
            residual_rms_m: None,
            condition_score: None,
            used_edges: vec![],
            rejected_edges: rejected,
            reason: Some(if temporal_failure {
                "All available pairwise range constraints are stale/replayed/temporally invalid"
                    .into()
            } else {
                "No defensible inter-node distance edge yet".into()
            }),
        });
    }

    let axis = best_axis(&anchor, &component, &edges)?;
    let axis_edge = edge_lookup(&edges, &anchor, &axis)?;
    let variance = axis_edge.sigma.powi(2);
    let axis_positions = vec![
        NodePositionEstimate {
            node_id: anchor.clone(),
            x_m: 0.0,
            y_m: 0.0,
            z_m: 0.0,
            covariance_2x2: [[variance, 0.0], [0.0, variance]],
            error_radius_95_m: 2.4477 * axis_edge.sigma,
        },
        NodePositionEstimate {
            node_id: axis.clone(),
            x_m: axis_edge.distance,
            y_m: 0.0,
            z_m: 0.0,
            covariance_2x2: [[variance, 0.0], [0.0, variance]],
            error_radius_95_m: 2.4477 * axis_edge.sigma,
        },
    ];

    if component.len() < 3 || edges.len() < (2 * component.len()).saturating_sub(3) {
        return Some(GeometrySolution {
            frame_id: format!("bf2-{anchor}-{axis}"),
            revision: revision_hash(&edges),
            generated_monotonic_ns: generated,
            dimension: GeometryDimension::OneD,
            state: GeometryState::Geometry1d,
            anchor_node_id: anchor,
            axis_node_id: Some(axis),
            positions: axis_positions,
            residual_rms_m: Some(0.0),
            condition_score: Some(0.0),
            used_edges: vec![axis_edge.id.clone()],
            rejected_edges: rejected,
            reason: Some(
                "Only a 1D baseline is observable; more independent range edges are required for 2D"
                    .into(),
            ),
        });
    }

    let Some((mut positions, third)) = initialize_positions(&component, &edges, &anchor, &axis)
    else {
        return Some(GeometrySolution {
            frame_id: format!("bf2-{anchor}-{axis}"),
            revision: revision_hash(&edges),
            generated_monotonic_ns: generated,
            dimension: GeometryDimension::OneD,
            state: GeometryState::GeometryInsufficient,
            anchor_node_id: anchor,
            axis_node_id: Some(axis),
            positions: axis_positions,
            residual_rms_m: None,
            condition_score: Some(0.0),
            used_edges: vec![axis_edge.id.clone()],
            rejected_edges: rejected,
            reason: Some(
                "Range graph is degenerate or nearly collinear; refusing to manufacture a 2D layout"
                    .into(),
            ),
        });
    };

    optimize_positions(&mut positions, &edges, &anchor, &axis, &third);

    let mut kept = Vec::new();
    for edge in &edges {
        let (Some(a), Some(b)) = (positions.get(&edge.a), positions.get(&edge.b)) else {
            continue;
        };
        let residual = (((a.0 - b.0).powi(2) + (a.1 - b.1).powi(2)).sqrt()
            - edge.distance)
            .abs();
        let threshold = (3.0 * edge.sigma).max(1.0).max(0.35 * edge.distance);
        if residual > threshold {
            rejected.push(RejectedEdge {
                edge_id: edge.id.clone(),
                reason: "persistent solver outlier".into(),
                residual_m: Some(residual),
            });
        } else {
            kept.push(edge.clone());
        }
    }
    if kept.len() >= (2 * positions.len()).saturating_sub(3) && kept.len() < edges.len() {
        edges = kept;
        optimize_positions(&mut positions, &edges, &anchor, &axis, &third);
    }

    let residuals: Vec<f64> = edges
        .iter()
        .filter_map(|edge| {
            let a = positions.get(&edge.a)?;
            let b = positions.get(&edge.b)?;
            Some(
                ((a.0 - b.0).powi(2) + (a.1 - b.1).powi(2)).sqrt() - edge.distance,
            )
        })
        .collect();
    let residual_rms = if residuals.is_empty() {
        None
    } else {
        Some(
            (residuals.iter().map(|residual| residual * residual).sum::<f64>()
                / residuals.len() as f64)
                .sqrt(),
        )
    };

    let values: Vec<_> = positions.values().copied().collect();
    let mut max_span = 0.1_f64;
    let mut max_cross = 0.0_f64;
    for i in 0..values.len() {
        for j in i + 1..values.len() {
            max_span = max_span.max(
                ((values[i].0 - values[j].0).powi(2) + (values[i].1 - values[j].1).powi(2))
                    .sqrt(),
            );
            for k in j + 1..values.len() {
                let a = values[i];
                let b = values[j];
                let c = values[k];
                max_cross = max_cross.max(
                    ((b.0 - a.0) * (c.1 - a.1) - (b.1 - a.1) * (c.0 - a.0)).abs(),
                );
            }
        }
    }
    let condition = (max_cross / (max_span * max_span) / 0.35).clamp(0.0, 1.0);
    let rms = residual_rms.unwrap_or(0.0);
    let disconnected = positions.len() < node_ids.len();
    let degraded = disconnected || condition < 0.18 || rms > 2.5;

    let mut estimates = Vec::new();
    for (id, (x, y)) in &positions {
        let information = edges
            .iter()
            .filter(|edge| edge.a == *id || edge.b == *id)
            .map(|edge| edge.quality_weight / edge.sigma.powi(2).max(0.04))
            .sum::<f64>();
        let sigma = (1.0 / information.max(0.05)).sqrt().max(0.15)
            + rms * 0.5
            + (1.0 - condition) * 0.5;
        estimates.push(NodePositionEstimate {
            node_id: id.clone(),
            x_m: *x,
            y_m: *y,
            z_m: 0.0,
            covariance_2x2: [[sigma * sigma, 0.0], [0.0, sigma * sigma]],
            error_radius_95_m: 2.4477 * sigma,
        });
    }
    estimates.sort_by(|a, b| a.node_id.cmp(&b.node_id));

    let reason = if disconnected {
        Some(format!(
            "Solved {}/{} active nodes; disconnected/unobservable nodes remain unresolved",
            positions.len(),
            node_ids.len()
        ))
    } else if condition < 0.18 {
        Some("Geometry is poorly conditioned / nearly collinear".into())
    } else if rms > 2.5 {
        Some("Range residuals exceed the reliable geometry threshold".into())
    } else {
        None
    };

    Some(GeometrySolution {
        frame_id: format!("bf2-{anchor}-{axis}"),
        revision: revision_hash(&edges),
        generated_monotonic_ns: generated,
        dimension: GeometryDimension::TwoD,
        state: if degraded {
            GeometryState::GeometryDegraded
        } else {
            GeometryState::Geometry2d
        },
        anchor_node_id: anchor,
        axis_node_id: Some(axis),
        positions: estimates,
        residual_rms_m: residual_rms,
        condition_score: Some(condition),
        used_edges: edges.iter().map(|edge| edge.id.clone()).collect(),
        rejected_edges: rejected,
        reason,
    })
}

pub fn published_geometry_from_coordinator(
    nodes: &[NodeAdvertisement],
    coordinator_node_id: &str,
) -> Option<GeometrySolution> {
    let node = nodes
        .iter()
        .find(|candidate| candidate.node_id == coordinator_node_id)?;
    if node.protocol_version != PROTOCOL_VERSION
        || node.geometry_publisher_node_id.as_deref() != Some(coordinator_node_id)
    {
        return None;
    }
    node.published_geometry.clone()
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

pub fn estimate_from_rssi_with_geometry(
    nodes: &[NodeAdvertisement],
    geometry: &GeometrySolution,
) -> Option<HumanEstimate> {
    if !matches!(geometry.dimension, GeometryDimension::TwoD)
        || matches!(
            geometry.state,
            GeometryState::GeometryInsufficient | GeometryState::GeometryStale
        )
    {
        return None;
    }
    let positions: HashMap<&str, &NodePositionEstimate> = geometry
        .positions
        .iter()
        .map(|position| (position.node_id.as_str(), position))
        .collect();
    let mut usable = Vec::new();
    for node in nodes {
        if !node.scanning {
            continue;
        }
        let Some(position) = positions.get(node.node_id.as_str()).copied() else {
            continue;
        };
        let Some(anomaly) = node.anomaly_z() else {
            continue;
        };
        if anomaly >= 0.75 {
            usable.push((node, position, anomaly));
        }
    }
    if usable.len() < 3 {
        return None;
    }
    let sum_weight: f64 = usable
        .iter()
        .map(|(_, _, anomaly)| (anomaly - 0.5).max(0.1))
        .sum();
    if sum_weight <= 0.0 {
        return None;
    }
    let x = usable
        .iter()
        .map(|(_, position, anomaly)| position.x_m * (anomaly - 0.5).max(0.1))
        .sum::<f64>()
        / sum_weight;
    let y = usable
        .iter()
        .map(|(_, position, anomaly)| position.y_m * (anomaly - 0.5).max(0.1))
        .sum::<f64>()
        / sum_weight;
    let variance_x = usable
        .iter()
        .map(|(_, position, anomaly)| {
            let weight = (anomaly - 0.5).max(0.1);
            weight * ((position.x_m - x).powi(2) + position.covariance_2x2[0][0])
        })
        .sum::<f64>()
        / sum_weight;
    let variance_y = usable
        .iter()
        .map(|(_, position, anomaly)| {
            let weight = (anomaly - 0.5).max(0.1);
            weight * ((position.y_m - y).powi(2) + position.covariance_2x2[1][1])
        })
        .sum::<f64>()
        / sum_weight;
    let penalty = geometry.residual_rms_m.unwrap_or(1.0)
        + 1.5 * (1.0 - geometry.condition_score.unwrap_or(0.0));
    let sigma_radial = (variance_x + variance_y).sqrt().max(0.5) + 0.5 * penalty;
    let error_95 = (2.4477 * sigma_radial).max(1.0);
    let range = (x * x + y * y).sqrt();
    let uncertainty = (100.0 * error_95 / range.max(2.0)).clamp(0.0, 100.0);
    let mean_anomaly = usable
        .iter()
        .map(|(_, _, anomaly)| *anomaly)
        .sum::<f64>()
        / usable.len() as f64;
    let confidence = (1.0 - (-0.35 * (mean_anomaly - 0.75).max(0.0)).exp()).clamp(0.0, 0.95);
    let state = if mean_anomaly >= 5.0 {
        "PROBABLE_HUMAN"
    } else {
        "POSSIBLE_HUMAN"
    };
    let quality = if uncertainty <= 20.0 {
        "HIGH"
    } else if uncertainty <= 40.0 {
        "MEDIUM"
    } else if uncertainty <= 70.0 {
        "LOW"
    } else {
        "VERY_LOW"
    };
    Some(HumanEstimate {
        method: "EXPERIMENTAL_RSSI_DISTURBANCE_AUTOGEOMETRY_V2".into(),
        state: state.into(),
        x_m: x,
        y_m: y,
        z_m: 0.0,
        range_m: range,
        bearing_deg: x.atan2(y).to_degrees(),
        human_confidence: confidence,
        uncertainty_percent: uncertainty,
        error_radius_95_m: error_95,
        evidence_quality: quality.into(),
        covariance_2x2: [[variance_x, 0.0], [0.0, variance_y]],
        provenance: usable
            .into_iter()
            .map(|(node, _, anomaly)| EvidenceContribution {
                node_id: node.node_id.clone(),
                source: "WIFI_RSSI_DISTURBANCE".into(),
                anomaly_z: anomaly,
                weight: (anomaly - 0.5).max(0.1) / sum_weight,
            })
            .collect(),
    })
}

pub fn estimate_from_rssi(nodes: &[NodeAdvertisement]) -> Option<HumanEstimate> {
    let geometry = solve_geometry(nodes)?;
    estimate_from_rssi_with_geometry(nodes, &geometry)
}

pub fn elect_coordinator(nodes: &[NodeAdvertisement]) -> Option<String> {
    nodes
        .iter()
        .filter(|node| node.protocol_version == PROTOCOL_VERSION)
        .max_by(|a, b| {
            a.coordinator_score
                .partial_cmp(&b.coordinator_score)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| b.node_id.cmp(&a.node_id))
        })
        .map(|node| node.node_id.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn obs(a: &str, b: &str, distance: f64) -> PairwiseRangeObservation {
        PairwiseRangeObservation {
            session_id: "test".into(),
            observer_node_id: a.into(),
            peer_node_id: b.into(),
            technology: RangingTechnology::BleRssi,
            monotonic_ns: 1_000_000_000,
            distance_m: Some(distance),
            distance_sigma_m: Some(0.25),
            azimuth_deg: None,
            azimuth_sigma_deg: None,
            elevation_deg: None,
            elevation_sigma_deg: None,
            rssi_dbm: Some(-60.0),
            quality: MeasurementQuality::Medium,
            source_detail: "fixture".into(),
        }
    }

    fn node(id: &str, ranges: Vec<PairwiseRangeObservation>, rssi: f64) -> NodeAdvertisement {
        NodeAdvertisement {
            protocol_version: PROTOCOL_VERSION,
            session_id: "test".into(),
            node_id: id.into(),
            display_name: id.into(),
            platform: "test".into(),
            monotonic_ns: 1_000_000_000,
            coordinator_score: 0.5,
            capabilities: BTreeMap::new(),
            rssi_dbm: Some(rssi),
            baseline_rssi_dbm: Some(-50.0),
            baseline_sigma_db: Some(1.0),
            position: None,
            scanning: true,
            ble_identity: None,
            ranges,
            manual_geometry_override: false,
            published_geometry: None,
            geometry_publisher_node_id: None,
        }
    }

    fn triangle() -> Vec<NodeAdvertisement> {
        vec![
            node(
                "a",
                vec![obs("a", "b", 3.0), obs("a", "c", 4.0)],
                -60.0,
            ),
            node(
                "b",
                vec![obs("b", "a", 3.0), obs("b", "c", 5.0)],
                -58.0,
            ),
            node(
                "c",
                vec![obs("c", "a", 4.0), obs("c", "b", 5.0)],
                -56.0,
            ),
        ]
    }

    #[test]
    fn two_nodes_are_only_1d() {
        let nodes = vec![
            node("a", vec![obs("a", "b", 2.0)], -60.0),
            node("b", vec![obs("b", "a", 2.0)], -60.0),
        ];
        let geometry = solve_geometry(&nodes).expect("geometry");
        assert_eq!(geometry.dimension, GeometryDimension::OneD);
        assert_eq!(geometry.positions.len(), 2);
    }

    #[test]
    fn triangle_solves_without_manual_coordinates() {
        let geometry = solve_geometry(&triangle()).expect("geometry");
        assert_eq!(geometry.dimension, GeometryDimension::TwoD);
        assert_eq!(geometry.positions.len(), 3);
        assert!(geometry
            .positions
            .iter()
            .all(|position| position.error_radius_95_m > 0.0));
    }

    #[test]
    fn human_estimate_consumes_auto_geometry() {
        let nodes = triangle();
        let geometry = solve_geometry(&nodes).expect("geometry");
        let estimate = estimate_from_rssi_with_geometry(&nodes, &geometry).expect("estimate");
        assert!(estimate.method.contains("AUTOGEOMETRY"));
        assert_eq!(estimate.provenance.len(), 3);
    }

    #[test]
    fn protocol_round_trip() {
        let mut nodes = triangle();
        let node = nodes.remove(0);
        let serialized = serde_json::to_string(&node).expect("serialize");
        let decoded: NodeAdvertisement = serde_json::from_str(&serialized).expect("deserialize");
        assert_eq!(decoded, node);
    }
}
