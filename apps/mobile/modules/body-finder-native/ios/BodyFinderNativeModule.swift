import ExpoModulesCore
import Foundation

private final class BodyFinderIOSRuntime {
  static let shared = BodyFinderIOSRuntime()
  var nodeId: String
  var displayName: String = "iOS"
  var sessionId: String = "body-finder-lab"
  var baseline: Double?
  var sigma: Double?
  var scanning = false
  var running = false
  var publishedGeometry: [String: Any]?
  let startedNs = DispatchTime.now().uptimeNanoseconds

  private init() {
    let defaults = UserDefaults.standard
    if let saved = defaults.string(forKey: "body-finder-node-id-v2") {
      nodeId = saved
    } else {
      let id = "ios-" + UUID().uuidString.lowercased()
      defaults.set(id, forKey: "body-finder-node-id-v2")
      nodeId = id
    }
  }
}

private func jsonString(_ object: Any) -> String {
  guard JSONSerialization.isValidJSONObject(object),
        let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]),
        let text = String(data: data, encoding: .utf8) else { return "{}" }
  return text
}

private func geometryDictionary(_ text: String?) -> [String: Any]? {
  guard let text, let data = text.data(using: .utf8),
        let object = try? JSONSerialization.jsonObject(with: data),
        let dictionary = object as? [String: Any] else { return nil }
  return dictionary
}

public class BodyFinderNativeModule: Module {
  public func definition() -> ModuleDefinition {
    Name("BodyFinderNative")

    Function("getCapabilitiesJson") {
      #if targetEnvironment(simulator)
      let bleState = "UNSUPPORTED"
      let bleDetail = "iOS Simulator has no physical BLE ranging radio; this artifact validates application/native-module build and UI behavior only"
      #else
      let bleState = "SUPPORTED_UNVERIFIED"
      let bleDetail = "CoreBluetooth hardware may be available on a physical iOS device, but pairwise ranging/fabric is not validated in this release"
      #endif
      return jsonString([
        "platform": "ios",
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
        "capabilities": [
          "wifi_rssi": ["state": "UNSUPPORTED", "detail": "General connected-link Wi-Fi RSSI is not exposed by this adapter"],
          "wifi_rtt": ["state": "UNSUPPORTED", "detail": "No verified public iOS Wi-Fi RTT adapter in this release"],
          "ble_peer_ranging": ["state": bleState, "detail": bleDetail],
          "automatic_geometry_compute": ["state": "WORKING", "detail": "Protocol-v2 automatic geometry solver runs in the shared application layer"],
          "geometry_publication": ["state": "WORKING", "detail": "The shared UI can attach an elected-coordinator GeometrySolution to its local advertisement; simulator has no cross-device RF fabric"],
          "csi": ["state": "UNSUPPORTED", "detail": "No verified iOS CSI path; RSSI is never labeled CSI"],
          "udp_fabric": ["state": "UNSUPPORTED", "detail": "Cross-platform physical-iOS field fabric is not implemented in experimental.4; do not treat simulator participation as RF validation"],
          "compute": ["state": "WORKING", "detail": "Body Finder React Native / Expo runtime"]
        ]
      ])
    }

    Function("getDiagnosticsJson") {
      #if targetEnvironment(simulator)
      let detail = "iOS Simulator has no physical BLE/fabric participation; diagnostics are truthful build/UI placeholders"
      #else
      let detail = "Physical iOS BLE/fabric diagnostics are not implemented/validated in experimental.4"
      #endif
      return jsonString([
        "ble_diagnostics": [
          "scan_state": "UNSUPPORTED",
          "advertise_state": "UNSUPPORTED",
          "scan_mode": "NONE",
          "total_scan_results": 0,
          "body_finder_scan_results": 0,
          "malformed_body_finder_payloads": 0,
          "self_scan_results_ignored": 0,
          "last_any_scan_result_age_ms": NSNull(),
          "last_body_finder_scan_result_age_ms": NSNull(),
          "peers": [] as [Any],
          "system_ranging": [
            "state": "UNSUPPORTED",
            "detail": detail,
            "fresh_result_available": false
          ]
        ],
        "fabric_diagnostics": [
          "socket_state": "UNSUPPORTED",
          "multicast_join_state": "UNSUPPORTED",
          "tx_packets": 0,
          "rx_packets": 0,
          "rx_protocol_v2_packets": 0,
          "rx_same_session_packets": 0,
          "peer_count_active": 0,
          "peer_expire_count": 0,
          "peers": [] as [Any]
        ]
      ])
    }

    Function("getWifiRssi") { return nil as Double? }

    Function("updateLocalState") { (baseline: Double?, sigma: Double?, scanning: Bool) -> Bool in
      let runtime = BodyFinderIOSRuntime.shared
      runtime.baseline = baseline
      runtime.sigma = sigma
      runtime.scanning = scanning
      return true
    }

    Function("updatePublishedGeometry") { (publish: Bool, geometryJson: String?) -> Bool in
      let runtime = BodyFinderIOSRuntime.shared
      runtime.publishedGeometry = publish ? geometryDictionary(geometryJson) : nil
      return true
    }

    AsyncFunction("startFabric") { (nodeId: String?, displayName: String?, sessionId: String?) -> Bool in
      let runtime = BodyFinderIOSRuntime.shared
      if let supplied = nodeId, !supplied.isEmpty { runtime.nodeId = supplied }
      if let supplied = displayName, !supplied.isEmpty { runtime.displayName = supplied }
      if let supplied = sessionId, !supplied.isEmpty { runtime.sessionId = supplied }
      runtime.running = true
      return true
    }

    Function("stopFabric") {
      let runtime = BodyFinderIOSRuntime.shared
      runtime.running = false
      runtime.publishedGeometry = nil
      return true
    }

    Function("getPeersJson") { return "[]" }

    Function("getLocalAdvertisementJson") {
      let runtime = BodyFinderIOSRuntime.shared
      let baseline: Any = runtime.baseline.map { $0 as Any } ?? NSNull()
      let sigma: Any = runtime.sigma.map { $0 as Any } ?? NSNull()
      let elapsed = DispatchTime.now().uptimeNanoseconds &- runtime.startedNs
      var advertisement: [String: Any] = [
        "protocol_version": 2,
        "session_id": runtime.sessionId,
        "node_id": runtime.nodeId,
        "display_name": runtime.displayName,
        "platform": "ios",
        "monotonic_ns": elapsed,
        "coordinator_score": 0.70,
        "capabilities": [:] as [String: Any],
        "rssi_dbm": NSNull(),
        "baseline_rssi_dbm": baseline,
        "baseline_sigma_db": sigma,
        "position": NSNull(),
        "scanning": runtime.scanning,
        "ble_identity": NSNull(),
        "ranges": [] as [Any],
        "manual_geometry_override": false
      ]
      if let geometry = runtime.publishedGeometry {
        advertisement["geometry_publisher_node_id"] = runtime.nodeId
        advertisement["published_geometry"] = geometry
      } else {
        advertisement["geometry_publisher_node_id"] = NSNull()
        advertisement["published_geometry"] = NSNull()
      }
      return jsonString(advertisement)
    }
  }
}
