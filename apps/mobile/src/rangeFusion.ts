import type { Advertisement, RangeObservation } from './autogeometry';

export type ReciprocalFusionState = 'AGREE' | 'DEGRADED' | 'REJECT' | 'SINGLE_DIRECTION';
export type RangeTemporalState = 'FRESH' | 'HOLDOVER';

export type ReciprocalFusionDiagnostic = {
  pair_key: string;
  technology: string;
  fusion_mode: 'RECIPROCAL_INVERSE_VARIANCE' | 'SINGLE_DIRECTION_CONSERVATIVE' | 'REJECTED_DISAGREEMENT';
  source_observation_count: number;
  source_observers: string[];
  source_temporal_states: string[];
  temporal_state: RangeTemporalState | null;
  oldest_source_age_ms: number | null;
  reciprocal_delta_m: number | null;
  reciprocal_state: ReciprocalFusionState;
  distance_m: number | null;
  sigma_m: number | null;
  calibration_profile_id: string | null;
};

const STALE_NS = 8_000_000_000;
const REORDER_TOLERANCE_NS = 250_000_000;
const HOLDOVER_MAX_MS = 10_000;
const canonicalPair = (a: string, b: string): [string, string] => a <= b ? [a, b] : [b, a];
const finitePositive = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0;

type TimedObservation = { observation: RangeObservation; age_ms: number };

function temporalState(observation: RangeObservation): string {
  const state = (observation as any).range_temporal_state;
  return typeof state === 'string' ? state : 'FRESH';
}

function metricBle(observation: RangeObservation): boolean {
  const ext = observation as any;
  const temporal = temporalState(observation);
  return observation.technology === 'BLE_RSSI'
    && ext.metric_valid === true
    && ext.range_status === 'VALID_METRIC'
    && (temporal === 'FRESH' || temporal === 'HOLDOVER')
    && finitePositive(observation.distance_m)
    && finitePositive(observation.distance_sigma_m);
}

function observationAgeMs(node: Advertisement, observation: RangeObservation): number {
  const explicit = (observation as any).range_age_ms;
  if (typeof explicit === 'number' && Number.isFinite(explicit) && explicit >= 0) return explicit;
  const now = node.monotonic_ns;
  if (typeof now !== 'number' || !Number.isFinite(now)) return 0;
  return Math.max(0, now - observation.monotonic_ns) / 1_000_000;
}

function freshForContainer(node: Advertisement, observation: RangeObservation): boolean {
  if (observation.observer_node_id !== node.node_id || observation.session_id !== node.session_id) return false;
  const temporal = temporalState(observation);
  const ageMs = observationAgeMs(node, observation);
  if (temporal === 'HOLDOVER') return ageMs <= HOLDOVER_MAX_MS;
  const now = node.monotonic_ns;
  if (typeof now !== 'number' || !Number.isFinite(now)) return true;
  if (observation.monotonic_ns > now + REORDER_TOLERANCE_NS) return false;
  return Math.max(0, now - observation.monotonic_ns) <= STALE_NS;
}

function latestPerObserver(samples: TimedObservation[]) {
  const latest = new Map<string, TimedObservation>();
  for (const sample of samples) {
    const current = latest.get(sample.observation.observer_node_id);
    if (!current || sample.observation.monotonic_ns > current.observation.monotonic_ns) {
      latest.set(sample.observation.observer_node_id, sample);
    }
  }
  return [...latest.values()].sort((a, b) => a.observation.observer_node_id.localeCompare(b.observation.observer_node_id));
}

export function applyReciprocalFusion(input: Advertisement[]): {
  nodes: Advertisement[];
  diagnostics: ReciprocalFusionDiagnostic[];
} {
  const nodes = input.map(node => ({ ...node, ranges: [...(node.ranges ?? [])] }));
  const groups = new Map<string, TimedObservation[]>();

  for (const node of input) {
    for (const observation of node.ranges ?? []) {
      if (!metricBle(observation) || !freshForContainer(node, observation)) continue;
      const [a, b] = canonicalPair(observation.observer_node_id, observation.peer_node_id);
      const key = `${a}\u0000${b}\u0000BLE_RSSI`;
      groups.set(key, [...(groups.get(key) ?? []), { observation, age_ms: observationAgeMs(node, observation) }]);
    }
  }

  // Only fresh or explicitly bounded HOLDOVER metric BLE observations are replaced.
  // Raw advertisements stay untouched outside this cloned solver input.
  for (const node of nodes) {
    node.ranges = (node.ranges ?? []).filter(observation => !(metricBle(observation) && freshForContainer(node, observation)));
  }

  const diagnostics: ReciprocalFusionDiagnostic[] = [];
  for (const [key, grouped] of groups) {
    const [a, b, technology] = key.split('\u0000');
    const timed = latestPerObserver(grouped);
    const samples = timed.map(item => item.observation);
    const ages = timed.map(item => item.age_ms);
    const sourceTemporalStates = samples.map(temporalState);
    const fusedTemporalState: RangeTemporalState = sourceTemporalStates.some(state => state === 'HOLDOVER') ? 'HOLDOVER' : 'FRESH';
    const oldestSourceAgeMs = ages.length ? Math.max(...ages) : 0;
    const profiles = [...new Set(samples.map(sample => (sample as any).calibration_profile_id).filter(Boolean))];
    const profileId = profiles.length === 1 ? String(profiles[0]) : null;
    const target = nodes.find(node => node.node_id === a);
    if (!target || !samples.length) continue;
    const syntheticMonotonicNs = typeof target.monotonic_ns === 'number' && Number.isFinite(target.monotonic_ns)
      ? target.monotonic_ns
      : samples.find(sample => sample.observer_node_id === a)?.monotonic_ns ?? samples[0].monotonic_ns;

    if (samples.length >= 2) {
      const first = samples[0];
      const second = samples[1];
      const d1 = first.distance_m!;
      const d2 = second.distance_m!;
      const s1 = Math.max(1.0, first.distance_sigma_m!);
      const s2 = Math.max(1.0, second.distance_sigma_m!);
      const delta = Math.abs(d1 - d2);
      const degradedThreshold = Math.max(1.0, 1.5 * Math.max(s1, s2));
      const rejectThreshold = Math.max(2.5, 2.5 * Math.max(s1, s2));

      if (delta > rejectThreshold || profiles.length !== 1) {
        diagnostics.push({
          pair_key: `${a}::${b}`,
          technology,
          fusion_mode: 'REJECTED_DISAGREEMENT',
          source_observation_count: samples.length,
          source_observers: samples.map(sample => sample.observer_node_id),
          source_temporal_states: sourceTemporalStates,
          temporal_state: null,
          oldest_source_age_ms: oldestSourceAgeMs,
          reciprocal_delta_m: delta,
          reciprocal_state: 'REJECT',
          distance_m: null,
          sigma_m: null,
          calibration_profile_id: profileId,
        });
        continue;
      }

      const w1 = 1 / (s1 * s1);
      const w2 = 1 / (s2 * s2);
      const distance = (w1 * d1 + w2 * d2) / (w1 + w2);
      const nominalSigma = Math.sqrt(1 / (w1 + w2));
      const state: ReciprocalFusionState = delta > degradedThreshold ? 'DEGRADED' : 'AGREE';
      const sigma = state === 'DEGRADED'
        ? Math.max(1.0, nominalSigma, delta, Math.max(s1, s2))
        : Math.max(1.0, nominalSigma, 0.75 * Math.max(s1, s2));
      const fused = {
        ...first,
        observer_node_id: a,
        peer_node_id: b,
        monotonic_ns: syntheticMonotonicNs,
        source_observation_monotonic_ns: samples.map(sample => (sample as any).source_observation_monotonic_ns ?? sample.monotonic_ns),
        range_age_ms: oldestSourceAgeMs,
        range_temporal_state: fusedTemporalState,
        distance_m: distance,
        distance_sigma_m: sigma,
        quality: 'LOW',
        source_detail: `reciprocal BLE_RSSI inverse-variance fusion; temporal=${fusedTemporalState}; oldest_age_ms=${oldestSourceAgeMs.toFixed(0)}; state=${state}; delta=${delta.toFixed(3)}m; sources=${samples.map(sample => sample.observer_node_id).join(',')}; profile=${profileId}`,
        metric_valid: true,
        range_status: 'VALID_METRIC',
        calibration_profile_id: profileId,
        calibration_state: 'VALIDATED_COARSE',
        fusion_mode: 'RECIPROCAL_INVERSE_VARIANCE',
        source_observation_count: samples.length,
        source_observers: samples.map(sample => sample.observer_node_id),
        source_temporal_states: sourceTemporalStates,
        reciprocal_delta_m: delta,
        reciprocal_state: state,
      } as RangeObservation;
      target.ranges = [...(target.ranges ?? []), fused];
      diagnostics.push({
        pair_key: `${a}::${b}`,
        technology,
        fusion_mode: 'RECIPROCAL_INVERSE_VARIANCE',
        source_observation_count: samples.length,
        source_observers: samples.map(sample => sample.observer_node_id),
        source_temporal_states: sourceTemporalStates,
        temporal_state: fusedTemporalState,
        oldest_source_age_ms: oldestSourceAgeMs,
        reciprocal_delta_m: delta,
        reciprocal_state: state,
        distance_m: distance,
        sigma_m: sigma,
        calibration_profile_id: profileId,
      });
    } else {
      const sample = samples[0];
      const sigma = Math.max(1.5, (sample.distance_sigma_m ?? 1.5) * 1.25);
      const singleTemporal = temporalState(sample) === 'HOLDOVER' ? 'HOLDOVER' : 'FRESH';
      const single = {
        ...sample,
        observer_node_id: a,
        peer_node_id: b,
        monotonic_ns: syntheticMonotonicNs,
        range_age_ms: oldestSourceAgeMs,
        range_temporal_state: singleTemporal,
        distance_sigma_m: sigma,
        source_detail: `single-direction validated BLE_RSSI metric; temporal=${singleTemporal}; age_ms=${oldestSourceAgeMs.toFixed(0)}; conservative sigma inflation; original_observer=${sample.observer_node_id}; profile=${(sample as any).calibration_profile_id ?? 'unknown'}`,
        metric_valid: true,
        range_status: 'VALID_METRIC',
        fusion_mode: 'SINGLE_DIRECTION_CONSERVATIVE',
        source_observation_count: 1,
        source_observers: [sample.observer_node_id],
        source_temporal_states: [temporalState(sample)],
        reciprocal_delta_m: null,
        reciprocal_state: 'SINGLE_DIRECTION',
      } as RangeObservation;
      target.ranges = [...(target.ranges ?? []), single];
      diagnostics.push({
        pair_key: `${a}::${b}`,
        technology,
        fusion_mode: 'SINGLE_DIRECTION_CONSERVATIVE',
        source_observation_count: 1,
        source_observers: [sample.observer_node_id],
        source_temporal_states: [temporalState(sample)],
        temporal_state: singleTemporal,
        oldest_source_age_ms: oldestSourceAgeMs,
        reciprocal_delta_m: null,
        reciprocal_state: 'SINGLE_DIRECTION',
        distance_m: sample.distance_m,
        sigma_m: sigma,
        calibration_profile_id: typeof (sample as any).calibration_profile_id === 'string' ? (sample as any).calibration_profile_id : null,
      });
    }
  }

  diagnostics.sort((x, y) => x.pair_key.localeCompare(y.pair_key));
  return { nodes, diagnostics };
}
