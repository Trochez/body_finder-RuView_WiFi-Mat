import { requireNativeModule } from 'expo-modules-core';

export type NativeApi = {
  getCapabilitiesJson(): string;
  getDiagnosticsJson(): string;
  getWifiRssi(): number | null;
  updateLocalState(baseline: number | null, sigma: number | null, scanning: boolean): boolean;
  updatePublishedGeometry(publish: boolean, geometryJson: string | null): boolean;
  updateGeometryState(geometryState: string): boolean;
  updateAppVisibility(visibility: string): boolean;
  startValidationRun(): string;
  endValidationRun(): boolean;
  getValidationRunJson(): string;
  getCalibrationSnapshotJson(): string;
  startFabric(nodeId: string | null, displayName: string | null, sessionId: string | null): Promise<boolean>;
  stopFabric(): boolean;
  getPeersJson(): string;
  getLocalAdvertisementJson(): string;
};

const native = requireNativeModule<NativeApi>('BodyFinderNative');

function sanitizeCalibrationSnapshotJson(raw: string): string {
  try {
    const value = JSON.parse(raw);
    const walk = (node: any): any => {
      if (Array.isArray(node)) return node.map(walk);
      if (!node || typeof node !== 'object') return node;
      const out: any = {};
      for (const [key, child] of Object.entries(node)) {
        if (key === 'rssi_samples_dbm' && Array.isArray(child)) {
          out[key] = child.filter(sample => typeof sample === 'number' && Number.isFinite(sample) && sample !== 127 && sample >= -127 && sample <= 20);
        } else out[key] = walk(child);
      }
      return out;
    };
    return JSON.stringify(walk(value));
  } catch {
    return raw;
  }
}

const api: NativeApi = {
  ...native,
  getCalibrationSnapshotJson: () => sanitizeCalibrationSnapshotJson(native.getCalibrationSnapshotJson()),
};

export default api;
