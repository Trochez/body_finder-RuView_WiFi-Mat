use body_finder_core::{solve_geometry, CapabilityProbe, GeometryDimension, GeometryState, MeasurementQuality, NodeAdvertisement, PairwiseRangeObservation, RangingTechnology, PROTOCOL_VERSION};
use std::collections::BTreeMap;

fn range(observer: &str, peer: &str, distance: f64, sigma: f64) -> PairwiseRangeObservation {
    PairwiseRangeObservation {
        session_id: "acceptance".into(),
        observer_node_id: observer.into(),
        peer_node_id: peer.into(),
        technology: RangingTechnology::BleRssi,
        monotonic_ns: 1,
        distance_m: Some(distance),
        distance_sigma_m: Some(sigma),
        azimuth_deg: None,
        azimuth_sigma_deg: None,
        elevation_deg: None,
        elevation_sigma_deg: None,
        rssi_dbm: Some(-60.0),
        quality: MeasurementQuality::Medium,
        source_detail: "SIMULATED_TEST_FIXTURE".into(),
    }
}

fn node(id: &str, ranges: Vec<PairwiseRangeObservation>) -> NodeAdvertisement {
    let _unused_type_anchor: BTreeMap<String, CapabilityProbe> = BTreeMap::new();
    NodeAdvertisement {
        protocol_version: PROTOCOL_VERSION,
        session_id: "acceptance".into(),
        node_id: id.into(),
        display_name: id.into(),
        platform: "SIMULATED_TEST_FIXTURE".into(),
        monotonic_ns: 1,
        coordinator_score: 0.5,
        capabilities: BTreeMap::new(),
        rssi_dbm: Some(-60.0),
        baseline_rssi_dbm: Some(-50.0),
        baseline_sigma_db: Some(1.0),
        position: None,
        scanning: true,
        ble_identity: None,
        ranges,
        manual_geometry_override: false,
    }
}

fn triangle() -> Vec<NodeAdvertisement> {
    vec![
        node("a", vec![range("a", "b", 3.0, 0.2), range("a", "c", 4.0, 0.2)]),
        node("b", vec![range("b", "a", 3.0, 0.2), range("b", "c", 5.0, 0.2)]),
        node("c", vec![range("c", "a", 4.0, 0.2), range("c", "b", 5.0, 0.2)]),
    ]
}

#[test]
fn disconnected_node_is_not_given_a_fake_coordinate() {
    let mut nodes = triangle();
    nodes.push(node("d", vec![]));
    let g = solve_geometry(&nodes).expect("geometry result");
    assert_eq!(g.dimension, GeometryDimension::TwoD);
    assert_eq!(g.state, GeometryState::GeometryDegraded);
    assert_eq!(g.positions.len(), 3);
    assert!(g.positions.iter().all(|p| p.node_id != "d"));
    assert!(g.reason.as_deref().unwrap_or_default().contains("unresolved"));
}

#[test]
fn collinear_triangle_refuses_a_two_dimensional_solution() {
    let nodes = vec![
        node("a", vec![range("a", "b", 2.0, 0.1), range("a", "c", 4.0, 0.1)]),
        node("b", vec![range("b", "a", 2.0, 0.1), range("b", "c", 2.0, 0.1)]),
        node("c", vec![range("c", "a", 4.0, 0.1), range("c", "b", 2.0, 0.1)]),
    ];
    let g = solve_geometry(&nodes).expect("geometry result");
    assert_ne!(g.state, GeometryState::Geometry2d);
    assert!(matches!(g.dimension, GeometryDimension::OneD | GeometryDimension::Unknown));
}

#[test]
fn persistent_impossible_edge_does_not_silently_become_truth() {
    let mut nodes = triangle();
    nodes.push(node("d", vec![
        range("d", "a", 3.0, 0.2),
        range("d", "b", 4.0, 0.2),
        range("d", "c", 3.0, 0.2),
    ]));
    nodes[0].ranges.push(range("a", "d", 3.0, 0.2));
    nodes[1].ranges.push(range("b", "d", 4.0, 0.2));
    nodes[2].ranges.push(range("c", "d", 30.0, 0.05));
    let g = solve_geometry(&nodes).expect("geometry result");
    assert_eq!(g.dimension, GeometryDimension::TwoD);
    assert!(g.state == GeometryState::Geometry2d || g.state == GeometryState::GeometryDegraded);
    assert!(g.rejected_edges.iter().any(|e| e.edge_id.contains("c::d")) || g.residual_rms_m.unwrap_or(0.0) > 0.0);
}

#[test]
fn node_input_order_does_not_change_frame_identity_or_coordinates_materially() {
    let original = triangle();
    let mut reversed = original.clone();
    reversed.reverse();
    let a = solve_geometry(&original).expect("first solution");
    let b = solve_geometry(&reversed).expect("second solution");
    assert_eq!(a.frame_id, b.frame_id);
    assert_eq!(a.dimension, b.dimension);
    assert_eq!(a.state, b.state);
    assert_eq!(a.positions.len(), b.positions.len());
    for pa in &a.positions {
        let pb = b.positions.iter().find(|p| p.node_id == pa.node_id).expect("same node");
        assert!((pa.x_m - pb.x_m).abs() < 1e-8);
        assert!((pa.y_m - pb.y_m).abs() < 1e-8);
    }
}
