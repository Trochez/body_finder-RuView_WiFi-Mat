import ExpoModulesCore

public class BodyFinderNativeModule: Module {
  public func definition() -> ModuleDefinition {
    Name("BodyFinderNative")

    Function("getCapabilitiesJson") {
      return "{\"platform\":\"ios\",\"wifi_rssi\":{\"state\":\"UNSUPPORTED\",\"detail\":\"General Wi-Fi RSSI scanning is not exposed by this adapter\"},\"ble\":{\"state\":\"SUPPORTED_UNVERIFIED\",\"detail\":\"CoreBluetooth adapter planned; not human evidence in this build\"},\"imu\":{\"state\":\"SUPPORTED_UNVERIFIED\",\"detail\":\"CoreMotion available on physical devices\"},\"csi\":{\"state\":\"UNSUPPORTED\",\"detail\":\"No verified iOS CSI path\"},\"udp_fabric\":{\"state\":\"UNSUPPORTED\",\"detail\":\"iOS local fabric not implemented in experimental.1\"}}"
    }
    Function("getWifiRssi") { return nil as Double? }
    Function("updateLocalState") { (_: Double?, _: Double?, _: Double?, _: Double?, _: Bool) in return true }
    AsyncFunction("startFabric") { (_: String?, _: String?, _: String?) in return false }
    Function("stopFabric") { return true }
    Function("getPeersJson") { return "[]" }
    Function("getLocalAdvertisementJson") { return "{}" }
  }
}
