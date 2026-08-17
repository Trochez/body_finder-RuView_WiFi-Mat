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
          "csi": ["state": "UNSUPPORTED", "detail": "No verified iOS CSI path; RSSI is never labeled CSI"],
          "udp_fabric": ["state": "UNSUPPORTED", "detail": "Cross-platform iOS field fabric is not implemented in experimental.2; do not treat simulator participation as RF validation"],
          "compute": ["state": "WORKING", "detail": "Body Finder React Native / Expo runtime"]
        ]
      ])
    }

    Function("getWifiRssi") { return nil as Double? }

    Function("updateLocalState") { (baseline: Double?, sigma: Double?, scanning: Bool) -> Bool in
      let r = BodyFinderIOSRuntime.shared
      r.baseline = baseline
      r.sigma = sigma
      r.scanning = scanning
      return true
    }

    AsyncFunction("startFabric") { (nodeId: String?, displayName: String?, sessionId: String?) -> Bool in
      let r = BodyFinderIOSRuntime.shared
      if let supplied = nodeId, !supplied.isEmpty { r.nodeId = supplied }
      if let supplied = displayName, !supplied.isEmpty { r.displayName = supplied }
      if let supplied = sessionId, !supplied.isEmpty { r.sessionId = supplied }
      r.running = true
      return true
    }

    Function("stopFabric") {
      BodyFinderIOSRuntime.shared.running = false
      return true
    }

    Function("getPeersJson") { return "[]" }

    Function("getLocalAdvertisementJson") {
      let r = BodyFinderIOSRuntime.shared
      let baseline: Any = r.baseline ?? NSNull()
      let sigma: Any = r.sigma ?? NSNull()
      let elapsed = DispatchTime.now().uptimeNanoseconds &- r.startedNs
      return jsonString([
        "protocol_version": 2,
        "session_id": r.sessionId,
        "node_id": r.nodeId,
        "display_name": r.displayName,
        "platform": "ios",
        "monotonic_ns": elapsed,
        "coordinator_score": 0.70,
        "capabilities": [:] as [String: Any],
        "rssi_dbm": NSNull(),
        "baseline_rssi_dbm": baseline,
        "baseline_sigma_db": sigma,
        "position": NSNull(),
        "scanning": r.scanning,
        "ble_identity": NSNull(),
        "ranges": [] as [Any],
        "manual_geometry_override": false
      ])
    }
  }
}
