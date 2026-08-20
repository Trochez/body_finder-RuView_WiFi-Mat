import type { Advertisement } from './autogeometry';

export type RangeDiagnostic = {
  edge_id: string;
  observer_node_id: string;
  peer_node_id: string;
  technology: string;
  distance_m: number | null;
  raw_distance_m: number | null;
  sigma_m: number | null;
  sample_age_ms: number | null;
  quality: string;
  metric_valid: boolean;
  range_status: string | null;
  calibration_profile_id: string | null;
  calibration_state: string | null;
  proximity_band: string | null;
  source_detail: string;
};

export type GeometryGraphDiagnostics = {
  protocol_version: 2;
  active_session_id: string | null;
  connected_components: string[][];
  valid_edge_pairs: string[];
  metric_edge_pairs: string[];
  range_samples: RangeDiagnostic[];
  stale_sample_count: number;
  cross_session_sample_count: number;
  proximity_only_sample_count: number;
  saturated_sample_count: number;
  uncalibrated_sample_count: number;
  metric_sample_count: number;
  measurement_health: 'NO_METRIC_RANGE' | 'DEGRADED' | 'COARSE' | 'GOOD';
  physical_confidence: 'NONE' | 'LOW' | 'COARSE';
};

const STALE_NS = 8_000_000_000;

function preferredSession(nodes: Advertisement[]) {
  const counts = new Map<string, number>();
  for (const node of nodes) {
    if (node.protocol_version !== 2) continue;
    counts.set(node.session_id, (counts.get(node.session_id) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null;
}

export function diagnoseGeometryGraph(nodes: Advertisement[]): GeometryGraphDiagnostics {
  const session = preferredSession(nodes);
  const active = nodes.filter(node => node.protocol_version === 2 && node.session_id === session);
  const activeIds = new Set(active.map(node => node.node_id));
  const adjacency = new Map<string, Set<string>>();
  for (const id of [...activeIds].sort()) adjacency.set(id, new Set());

  const validPairs = new Set<string>();
  const metricPairs = new Set<string>();
  const samples: RangeDiagnostic[] = [];
  let stale = 0;
  let crossSession = 0;
  let proximityOnly = 0;
  let saturated = 0;
  let uncalibrated = 0;
  let metricSamples = 0;

  for (const node of active) {
    for (const observation of node.ranges ?? []) {
      const ext = observation as any;
      const a = observation.observer_node_id <= observation.peer_node_id
        ? observation.observer_node_id
        : observation.peer_node_id;
      const b = observation.observer_node_id <= observation.peer_node_id
        ? observation.peer_node_id
        : observation.observer_node_id;
      const edgeId = `${a}::${b}::${observation.technology}`;
      const sameSession = observation.session_id === session;
      const ageNs = node.monotonic_ns == null
        ? null
        : Math.max(0, node.monotonic_ns - observation.monotonic_ns);
      const isStale = ageNs != null && ageNs > STALE_NS;
      const metricValid = ext.metric_valid !== false
        && observation.distance_m != null
        && Number.isFinite(observation.distance_m);
      const status = typeof ext.range_status === 'string' ? ext.range_status : null;
      const calibrationState = typeof ext.calibration_state === 'string' ? ext.calibration_state : null;
      if (!sameSession) crossSession++;
      if (isStale) stale++;
      if (status === 'PROXIMITY_ONLY') proximityOnly++;
      if (status === 'SATURATED_HIGH' || status === 'SATURATED_LOW') saturated++;
      if (calibrationState?.includes('UNVALIDATED') || status === 'UNCALIBRATED') uncalibrated++;
      if (metricValid) metricSamples++;
      samples.push({
        edge_id: edgeId,
        observer_node_id: observation.observer_node_id,
        peer_node_id: observation.peer_node_id,
        technology: observation.technology,
        distance_m: observation.distance_m,
        raw_distance_m: typeof ext.raw_distance_m === 'number' ? ext.raw_distance_m : null,
        sigma_m: observation.distance_sigma_m,
        sample_age_ms: ageNs == null ? null : ageNs / 1_000_000,
        quality: observation.quality,
        metric_valid: metricValid,
        range_status: status,
        calibration_profile_id: typeof ext.calibration_profile_id === 'string' ? ext.calibration_profile_id : null,
        calibration_state: calibrationState,
        proximity_band: typeof ext.proximity_band === 'string' ? ext.proximity_band : null,
        source_detail: observation.source_detail,
      });

      const structurallyValid = sameSession
        && !isStale
        && observation.observer_node_id === node.node_id
        && observation.observer_node_id !== observation.peer_node_id
        && activeIds.has(observation.peer_node_id)
        && observation.quality !== 'REJECTED';
      if (structurallyValid) validPairs.add(`${a}::${b}`);

      const metricValidForGraph = structurallyValid
        && metricValid
        && observation.distance_m != null
        && observation.distance_m >= 0.05
        && observation.distance_m <= 100;
      if (metricValidForGraph) {
        adjacency.get(observation.observer_node_id)?.add(observation.peer_node_id);
        adjacency.get(observation.peer_node_id)?.add(observation.observer_node_id);
        metricPairs.add(`${a}::${b}`);
      }
    }
  }

  const seen = new Set<string>();
  const components: string[][] = [];
  for (const id of [...activeIds].sort()) {
    if (seen.has(id)) continue;
    const queue = [id];
    const component: string[] = [];
    seen.add(id);
    while (queue.length) {
      const current = queue.shift()!;
      component.push(current);
      for (const next of [...(adjacency.get(current) ?? [])].sort()) {
        if (!seen.has(next)) {
          seen.add(next);
          queue.push(next);
        }
      }
    }
    components.push(component.sort());
  }
  components.sort((a, b) => b.length - a.length || a.join('\0').localeCompare(b.join('\0')));
  samples.sort((a, b) => a.edge_id.localeCompare(b.edge_id) || a.observer_node_id.localeCompare(b.observer_node_id));

  const health: GeometryGraphDiagnostics['measurement_health'] = metricSamples === 0
    ? 'NO_METRIC_RANGE'
    : saturated > 0 || uncalibrated > 0
      ? 'DEGRADED'
      : metricPairs.size >= 3
        ? 'GOOD'
        : 'COARSE';
  const confidence: GeometryGraphDiagnostics['physical_confidence'] = metricSamples === 0
    ? 'NONE'
    : health === 'GOOD'
      ? 'COARSE'
      : 'LOW';

  return {
    protocol_version: 2,
    active_session_id: session,
    connected_components: components,
    valid_edge_pairs: [...validPairs].sort(),
    metric_edge_pairs: [...metricPairs].sort(),
    range_samples: samples,
    stale_sample_count: stale,
    cross_session_sample_count: crossSession,
    proximity_only_sample_count: proximityOnly,
    saturated_sample_count: saturated,
    uncalibrated_sample_count: uncalibrated,
    metric_sample_count: metricSamples,
    measurement_health: health,
    physical_confidence: confidence,
  };
}
