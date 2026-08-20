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
  var geometryState = "UNKNOWN"
  var appVisibility = "UNKNOWN"
  var validationRunId: String?
  var validationStartedAt: Date?
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
      let bleDetail = "Physical iOS pairwise ranging remains unvalidated in experimental.5"
      #endif
      return jsonString([
        "platform": "ios",
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
        "capabilities": [
          "wifi_rssi": ["state": "UNSUPPORTED", "detail": "General connected-link Wi-Fi RSSI is not exposed by this adapter"],
          "wifi_rtt": ["state": "UNSUPPORTED", "detail": "No verified public iOS Wi-Fi RTT adapter in this release"],
          "ble_peer_ranging": ["state": bleState, "detail": bleDetail],
          "ble_range_calibration": ["state": "UNSUPPORTED", "detail": "Android BLE RSSI screening profile does not apply to iOS"],
          "field_session_service": ["state": "UNSUPPORTED", "detail": "Android foreground-service lifecycle hardening is not an iOS capability"],
          "automatic_geometry_compute": ["state": "WORKING", "detail": "Protocol-v2 automatic geometry solver runs in the shared application layer"],
          "geometry_publication": ["state": "WORKING", "detail": "Shared UI can publish a GeometrySolution when metric constraints exist"],
          "csi": ["state": "UNSUPPORTED", "detail": "No verified iOS CSI path; RSSI is never labeled CSI"],
          "udp_fabric": ["state": "UNSUPPORTED", "detail": "Physical iOS field fabric remains unimplemented/unvalidated in experimental.5"],
          "compute": ["state": "WORKING", "detail": "Body Finder React Native / Expo runtime"]
        ]
      ])
    }

    Function("getDiagnosticsJson") {
      let runtime = BodyFinderIOSRuntime.shared
      #if targetEnvironment(simulator)
      let detail = "iOS Simulator has no physical BLE/fabric participation; diagnostics are truthful build/UI placeholders"
      #else
      let detail = "Physical iOS BLE/fabric diagnostics are not implemented/validated in experimental.5"
      #endif
      let validationElapsed: Any = runtime.validationStartedAt.map { Int(Date().timeIntervalSince($0) * 1000) as Any } ?? NSNull()
      return jsonString([
        "ble_diagnostics": [
          "scan_state": "UNSUPPORTED",
          "advertise_state": "UNSUPPORTED",
          "scan_mode": "NONE",
          "total_scan_results": 0,
          "body_finder_scan_results": 0,
          "peers": [] as [Any],
          "system_ranging": ["state": "UNSUPPORTED", "detail": detail, "fresh_result_available": false]
        ],
        "fabric_diagnostics": [
          "socket_state": "UNSUPPORTED",
          "multicast_join_state": "UNSUPPORTED",
          "tx_packets": 0,
          "rx_packets": 0,
          "peer_count_active": 0,
          "peer_expire_count": 0,
          "peers": [] as [Any]
        ],
        "lifecycle_diagnostics": [
          "foreground_service_state": "UNSUPPORTED",
          "app_visibility": runtime.appVisibility
        ],
        "validation_run": [
          "active": runtime.validationRunId != nil,
          "run_id": runtime.validationRunId as Any? ?? NSNull(),
          "elapsed_ms": validationElapsed,
          "current_geometry_state": runtime.geometryState,
          "physical_ios_validation": false
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

    Function("updateGeometryState") { (state: String) -> Bool in
      BodyFinderIOSRuntime.shared.geometryState = state
      return true
    }

    Function("updateAppVisibility") { (visibility: String) -> Bool in
      BodyFinderIOSRuntime.shared.appVisibility = visibility
      return true
    }

    Function("startValidationRun") {
      let runtime = BodyFinderIOSRuntime.shared
      let id = UUID().uuidString.lowercased()
      runtime.validationRunId = id
      runtime.validationStartedAt = Date()
      return id
    }

    Function("endValidationRun") {
      BodyFinderIOSRuntime.shared.validationRunId = nil
      return true
    }

    Function("getValidationRunJson") {
      let runtime = BodyFinderIOSRuntime.shared
      return jsonString([
        "active": runtime.validationRunId != nil,
        "run_id": runtime.validationRunId as Any? ?? NSNull(),
        "current_geometry_state": runtime.geometryState,
        "physical_ios_validation": false
      ])
    }

    Function("getCalibrationSnapshotJson") {
      let runtime = BodyFinderIOSRuntime.shared
      return jsonString([
        "schema_version": 1,
        "session_id": runtime.sessionId,
        "observer_node_id": runtime.nodeId,
        "peers": [] as [Any],
        "ground_truth_in_runtime": false,
        "detail": "No physical iOS BLE calibration adapter in experimental.5"
      ])
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
