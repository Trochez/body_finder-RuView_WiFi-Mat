use body_finder_core::NodeAdvertisement;

#[test]
fn android_wire_shape_is_rust_compatible() {
    let json = r#"{
      "protocol_version":1,
      "session_id":"body-finder-lab",
      "node_id":"android-test",
      "display_name":"Pixel",
      "platform":"android",
      "monotonic_ns":123,
      "coordinator_score":0.78,
      "capabilities":{
        "wifi_rssi":{"state":"WORKING","detail":"live connected-link RSSI read"},
        "wifi_rtt":{"state":"SUPPORTED_UNVERIFIED","detail":"feature present"},
        "csi":{"state":"UNSUPPORTED","detail":"no verified adapter"},
        "udp_fabric":{"state":"WORKING_DEGRADED","detail":"field verification required"}
      },
      "rssi_dbm":-55.0,
      "baseline_rssi_dbm":-51.0,
      "baseline_sigma_db":1.4,
      "position":{"x_m":1.0,"y_m":2.0,"z_m":0.0,"sigma_m":0.25},
      "scanning":true
    }"#;
    let ad: NodeAdvertisement =
        serde_json::from_str(json).expect("Android wire JSON must deserialize");
    assert_eq!(ad.node_id, "android-test");
    assert_eq!(ad.rssi_dbm, Some(-55.0));
    assert!(ad.capabilities.contains_key("wifi_rtt"));
}
