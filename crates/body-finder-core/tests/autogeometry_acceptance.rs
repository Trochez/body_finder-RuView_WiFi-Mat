use body_finder_core::{
    solve_geometry, CapabilityProbe, GeometryDimension, GeometryState, MeasurementQuality,
    NodeAdvertisement, PairwiseRangeObservation, RangingTechnology, PROTOCOL_VERSION,
    RANGE_SAMPLE_STALE_NS,
};
use std::collections::BTreeMap;

const NOW: u64 = 20_000_000_000;

fn range_with(
    observer: &str,
    peer: &str,
    distance: f64,
    sigma: f64,
    technology: RangingTechnology,
    monotonic_ns: u64,
) -> PairwiseRangeObservation {
    PairwiseRangeObservation {
        session_id: "acceptance".into(),
        observer_node_id: observer.into(),
        peer_node_id: peer.into(),
        technology,
        monotonic_ns,
        distance_m: Some(distance),
        distance_sigma_m: Some(sigma),
        azimuth_deg: None,
        azimuth_sigma_deg: None,
        elevation_deg: None,
        elevation_sigma_deg: None,
        rssi_dbm: Some(-60.0),
        quality: if matches!(technology, RangingTechnology::BleRssi) {
            MeasurementQuality::Low
        } else {
            MeasurementQuality::High
        },
        source_detail: "SIMULATED_TEST_FIXTURE".into(),
    }
}

fn range(observer: &str, peer: &str, distance: f64, sigma: f64) -> PairwiseRangeObservation {
    range_with(
        observer,
        peer,
        distance,
        sigma,
        RangingTechnology::BleRssi,
        NOW,
    )
}

fn node(id: &str, ranges: Vec<PairwiseRangeObservation>) -> NodeAdvertisement {
    let _unused_type_anchor: BTreeMap<String, CapabilityProbe> = BTreeMap::new();
    NodeAdvertisement {
        protocol_version: PROTOCOL_VERSION,
        session_id: "acceptance".into(),
        node_id: id.into(),
        display_name: id.into(),
        platform: "SIMULATED_TEST_FIXTURE".into(),
        monotonic_ns: NOW,
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
        published_geometry: None,
        geometry_publisher_node_id: None,
    }
}

fn triangle() -> Vec<NodeAdvertisement> {
    vec![
        node(
            "a",
            vec![range("a", "b", 3.0, 0.2), range("a", "c", 4.0, 0.2)],
        ),
        node(
            "b",
            vec![range("b", "a", 3.0, 0.2), range("b", "c", 5.0, 0.2)],
        ),
        node(
            "c",
            vec![range("c", "a", 4.0, 0.2), range("c", "b", 5.0, 0.2)],
        ),
    ]
}

#[test]
fn disconnected_node_is_not_given_a_fake_coordinate() {
    let mut nodes = triangle();
    nodes.push(node("d", vec![]));
    let geometry = solve_geometry(&nodes).expect("geometry result");
    assert_eq!(geometry.dimension, GeometryDimension::TwoD);
    assert_eq!(geometry.state, GeometryState::GeometryDegraded);
    assert_eq!(geometry.positions.len(), 3);
    assert!(geometry
        .positions
        .iter()
        .all(|position| position.node_id != "d"));
    assert!(geometry
        .reason
        .as_deref()
        .unwrap_or_default()
        .contains("unresolved"));
}

#[test]
fn collinear_triangle_refuses_a_two_dimensional_solution() {
    let nodes = vec![
        node(
            "a",
            vec![range("a", "b", 2.0, 0.1), range("a", "c", 4.0, 0.1)],
        ),
        node(
            "b",
            vec![range("b", "a", 2.0, 0.1), range("b", "c", 2.0, 0.1)],
        ),
        node(
            "c",
            vec![range("c", "a", 4.0, 0.1), range("c", "b", 2.0, 0.1)],
        ),
    ];
    let geometry = solve_geometry(&nodes).expect("geometry result");
    assert_ne!(geometry.state, GeometryState::Geometry2d);
    assert!(matches!(
        geometry.dimension,
        GeometryDimension::OneD | GeometryDimension::Unknown
    ));
}

#[test]
fn persistent_impossible_edge_does_not_silently_become_truth() {
    let mut nodes = triangle();
    nodes.push(node(
        "d",
        vec![
            range("d", "a", 3.0, 0.2),
            range("d", "b", 4.0, 0.2),
            range("d", "c", 3.0, 0.2),
        ],
    ));
    nodes[0].ranges.push(range("a", "d", 3.0, 0.2));
    nodes[1].ranges.push(range("b", "d", 4.0, 0.2));
    nodes[2].ranges.push(range("c", "d", 30.0, 0.05));
    let geometry = solve_geometry(&nodes).expect("geometry result");
    assert_eq!(geometry.dimension, GeometryDimension::TwoD);
    assert!(matches!(
        geometry.state,
        GeometryState::Geometry2d | GeometryState::GeometryDegraded
    ));
    assert!(
        geometry
            .rejected_edges
            .iter()
            .any(|edge| edge.edge_id.contains("c::d"))
            || geometry.residual_rms_m.unwrap_or(0.0) > 0.0
    );
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
    for position_a in &a.positions {
        let position_b = b
            .positions
            .iter()
            .find(|position| position.node_id == position_a.node_id)
            .expect("same node");
        assert!((position_a.x_m - position_b.x_m).abs() < 1e-8);
        assert!((position_a.y_m - position_b.y_m).abs() < 1e-8);
    }
}

#[test]
fn stale_ranges_expire_and_never_create_coordinates() {
    let stale_time = NOW - RANGE_SAMPLE_STALE_NS - 1;
    let nodes = vec![
        node(
            "a",
            vec![range_with(
                "a",
                "b",
                3.0,
                0.2,
                RangingTechnology::BleRssi,
                stale_time,
            )],
        ),
        node(
            "b",
            vec![range_with(
                "b",
                "a",
                3.0,
                0.2,
                RangingTechnology::BleRssi,
                stale_time,
            )],
        ),
    ];
    let geometry = solve_geometry(&nodes).expect("stale geometry result");
    assert_eq!(geometry.state, GeometryState::GeometryStale);
    assert_eq!(geometry.dimension, GeometryDimension::Unknown);
    assert!(geometry.positions.is_empty());
    assert!(geometry
        .rejected_edges
        .iter()
        .any(|edge| edge.reason.contains("stale")));
}

#[test]
fn replayed_out_of_order_sample_is_rejected() {
    let mut nodes = triangle();
    nodes[0].ranges.push(range_with(
        "a",
        "b",
        80.0,
        0.1,
        RangingTechnology::BleRssi,
        NOW - 1_000_000_000,
    ));
    let geometry = solve_geometry(&nodes).expect("geometry result");
    assert_eq!(geometry.dimension, GeometryDimension::TwoD);
    assert!(geometry
        .rejected_edges
        .iter()
        .any(|edge| edge.reason.contains("replayed/out-of-order")));
}

#[test]
fn cross_session_node_and_ranges_do_not_join_the_graph() {
    let mut nodes = triangle();
    let mut foreign = node("foreign", vec![range("foreign", "a", 1.0, 0.1)]);
    foreign.session_id = "other-session".into();
    foreign.ranges[0].session_id = "other-session".into();
    nodes.push(foreign);
    let geometry = solve_geometry(&nodes).expect("geometry result");
    assert_eq!(geometry.positions.len(), 3);
    assert!(geometry
        .positions
        .iter()
        .all(|position| position.node_id != "foreign"));
    assert!(geometry
        .rejected_edges
        .iter()
        .any(|edge| edge.reason.contains("cross-session")));
}

#[test]
fn higher_quality_ranging_source_wins_over_ble_for_same_pair() {
    let mut nodes = triangle();
    nodes[0].ranges.push(range_with(
        "a",
        "b",
        3.0,
        0.05,
        RangingTechnology::AndroidRangingUwb,
        NOW,
    ));
    nodes[1].ranges.push(range_with(
        "b",
        "a",
        3.0,
        0.05,
        RangingTechnology::AndroidRangingUwb,
        NOW,
    ));
    // Deliberately contradictory BLE edge. It must not be averaged with UWB.
    nodes[0].ranges[0].distance_m = Some(15.0);
    nodes[1].ranges[0].distance_m = Some(15.0);
    let geometry = solve_geometry(&nodes).expect("geometry result");
    assert!(geometry
        .used_edges
        .iter()
        .any(|edge| edge.contains("AndroidRangingUwb")));
    assert!(!geometry
        .used_edges
        .iter()
        .any(|edge| edge.contains("a::b::BleRssi")));
}
