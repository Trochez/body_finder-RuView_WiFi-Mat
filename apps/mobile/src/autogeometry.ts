export type RangeQuality = 'HIGH' | 'MEDIUM' | 'LOW' | 'REJECTED';
export type GeometryState =
  | 'DISCOVERING_NODES'
  | 'RANGING'
  | 'GEOMETRY_INSUFFICIENT'
  | 'GEOMETRY_1D'
  | 'GEOMETRY_2D'
  | 'GEOMETRY_DEGRADED'
  | 'GEOMETRY_STALE';

export type RangeObservation = {
  session_id: string;
  observer_node_id: string;
  peer_node_id: string;
  technology: string;
  monotonic_ns: number;
  distance_m: number | null;
  distance_sigma_m: number | null;
  azimuth_deg?: number | null;
  azimuth_sigma_deg?: number | null;
  elevation_deg?: number | null;
  elevation_sigma_deg?: number | null;
  rssi_dbm?: number | null;
  quality: RangeQuality;
  source_detail: string;
};

export type GeometryPosition = {
  node_id: string;
  x_m: number;
  y_m: number;
  z_m: number;
  error_radius_95_m: number;
  covariance_2x2: [[number, number], [number, number]];
};

export type GeometrySolution = {
  frame_id: string;
  revision: number;
  generated_monotonic_ns: number;
  dimension: 'UNKNOWN' | '1D' | '2D';
  state: GeometryState;
  anchor_node_id: string;
  axis_node_id: string | null;
  positions: GeometryPosition[];
  residual_rms_m: number | null;
  condition_score: number | null;
  used_edges: string[];
  rejected_edges: { edge_id: string; reason: string; residual_m?: number | null }[];
  reason: string | null;
};

export type Advertisement = {
  protocol_version: number;
  session_id: string;
  node_id: string;
  display_name: string;
  platform: string;
  monotonic_ns?: number;
  coordinator_score: number;
  rssi_dbm: number | null;
  baseline_rssi_dbm: number | null;
  baseline_sigma_db: number | null;
  position?: { x_m: number; y_m: number; z_m?: number; sigma_m?: number } | null;
  scanning: boolean;
  capabilities?: Record<string, unknown>;
  ble_identity?: string | null;
  ranges?: RangeObservation[];
  manual_geometry_override?: boolean;
  published_geometry?: (GeometrySolution & { authoritative_presence?: Record<string, unknown> }) | null;
  geometry_publisher_node_id?: string | null;
};

export type HumanEstimate = {
  x_m: number;
  y_m: number;
  range_m: number;
  bearing_deg: number;
  human_confidence: number;
  uncertainty_percent: number;
  error_radius_95_m: number;
  quality: string;
  method: string;
  state: string;
};

export type GeometrySelection = {
  solution: GeometrySolution | null;
  source:
    | 'LOCAL_ELECTED_COORDINATOR'
    | 'ELECTED_COORDINATOR_PUBLICATION'
    | 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION';
};

type Edge = {
  id: string;
  a: string;
  b: string;
  technology: string;
  d: number;
  sigma: number;
  q: number;
  latest: number;
};

type Rejected = GeometrySolution['rejected_edges'];

const PROTOCOL_VERSION = 2;
export const RANGE_SAMPLE_STALE_NS = 8_000_000_000;
export const RANGE_REORDER_TOLERANCE_NS = 250_000_000;

const qWeight = (quality: RangeQuality) =>
  quality === 'HIGH' ? 1 : quality === 'MEDIUM' ? 0.55 : quality === 'LOW' ? 0.18 : 0;
const pair = (a: string, b: string): [string, string] => (a <= b ? [a, b] : [b, a]);
const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

function preferredSession(nodes: Advertisement[]) {
  const counts = new Map<string, number>();
  for (const node of nodes) {
    if (node.protocol_version !== PROTOCOL_VERSION) continue;
    counts.set(node.session_id, (counts.get(node.session_id) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? null;
}

function activeNodes(nodes: Advertisement[], rejected: Rejected) {
  const session = preferredSession(nodes);
  if (!session) return [];
  return nodes.filter(node => {
    if (node.protocol_version !== PROTOCOL_VERSION) {
      rejected.push({
        edge_id: `node::${node.node_id}`,
        reason: `protocol mismatch: got ${node.protocol_version}, expected ${PROTOCOL_VERSION}`,
      });
      return false;
    }
    if (node.session_id !== session) {
      rejected.push({
        edge_id: `node::${node.node_id}`,
        reason: 'cross-session node advertisement rejected',
      });
      return false;
    }
    return true;
  });
}

function collectEdges(nodes: Advertisement[], rejected: Rejected) {
  const ids = new Set(nodes.map(node => node.node_id));
  const session = nodes[0]?.session_id ?? '';
  const latestBySource = new Map<string, number>();

  for (const node of nodes) {
    for (const observation of node.ranges ?? []) {
      if (observation.session_id !== session || observation.observer_node_id !== node.node_id) continue;
      const key = `${observation.observer_node_id}\u0000${observation.peer_node_id}\u0000${observation.technology}`;
      latestBySource.set(key, Math.max(latestBySource.get(key) ?? 0, observation.monotonic_ns));
    }
  }

  const groups = new Map<string, RangeObservation[]>();
  for (const node of nodes) {
    const observerNow = node.monotonic_ns ?? 0;
    for (const observation of node.ranges ?? []) {
      const [a, b] = pair(observation.observer_node_id, observation.peer_node_id);
      const edgeId = `${a}::${b}::${observation.technology}`;
      if (
        observation.session_id !== session ||
        observation.session_id !== node.session_id ||
        observation.observer_node_id !== node.node_id
      ) {
        rejected.push({ edge_id: edgeId, reason: 'session/observer identity mismatch' });
        continue;
      }
      if (!ids.has(observation.peer_node_id) || observation.peer_node_id === observation.observer_node_id) {
        rejected.push({ edge_id: edgeId, reason: 'peer not active in geometry graph' });
        continue;
      }
      if (observation.monotonic_ns > observerNow + RANGE_REORDER_TOLERANCE_NS) {
        rejected.push({
          edge_id: edgeId,
          reason: 'range sample timestamp is implausibly ahead of its observer',
        });
        continue;
      }
      const age = Math.max(0, observerNow - observation.monotonic_ns);
      if (age > RANGE_SAMPLE_STALE_NS) {
        rejected.push({ edge_id: edgeId, reason: 'stale range sample expired from geometry graph' });
        continue;
      }
      const sourceKey = `${observation.observer_node_id}\u0000${observation.peer_node_id}\u0000${observation.technology}`;
      const latest = latestBySource.get(sourceKey) ?? observation.monotonic_ns;
      if (latest - observation.monotonic_ns > RANGE_REORDER_TOLERANCE_NS) {
        rejected.push({ edge_id: edgeId, reason: 'replayed/out-of-order range sample rejected' });
        continue;
      }
      const distance = observation.distance_m;
      const sigma = observation.distance_sigma_m ?? 3;
      if (
        distance == null ||
        !Number.isFinite(distance) ||
        distance < 0.05 ||
        distance > 100 ||
        !Number.isFinite(sigma) ||
        sigma < 0.05 ||
        sigma > 30 ||
        qWeight(observation.quality) <= 0
      ) {
        rejected.push({ edge_id: edgeId, reason: 'invalid or rejected range sample' });
        continue;
      }
      const groupKey = `${a}\u0000${b}\u0000${observation.technology}`;
      groups.set(groupKey, [...(groups.get(groupKey) ?? []), observation]);
    }
  }

  const bestByPair = new Map<string, Edge>();
  for (const [key, samples] of groups) {
    const [a, b, technology] = key.split('\u0000');
    const distances = samples.map(sample => sample.distance_m!).filter(Number.isFinite);
    if (!distances.length) continue;
    const distance = median(distances);
    const mad = median(distances.map(value => Math.abs(value - distance)));
    const sigma = Math.max(
      0.15,
      median(samples.map(sample => sample.distance_sigma_m ?? 3)),
      1.4826 * mad,
    );
    const q = Math.max(...samples.map(sample => qWeight(sample.quality)));
    const candidate: Edge = {
      id: `${a}::${b}::${technology}`,
      a,
      b,
      technology,
      d: distance,
      sigma,
      q,
      latest: Math.max(...samples.map(sample => sample.monotonic_ns)),
    };
    const pairKey = `${a}\u0000${b}`;
    const current = bestByPair.get(pairKey);
    const score = candidate.q / Math.max(0.02, candidate.sigma ** 2);
    const currentScore = current ? current.q / Math.max(0.02, current.sigma ** 2) : -1;
    if (!current || score > currentScore || (Math.abs(score - currentScore) < 1e-12 && technology < current.technology)) {
      bestByPair.set(pairKey, candidate);
    }
  }
  return [...bestByPair.values()].sort((a, b) => a.id.localeCompare(b.id));
}

const edge = (edges: Edge[], a: string, b: string) => {
  const [x, y] = pair(a, b);
  return edges.find(candidate => candidate.a === x && candidate.b === y);
};

function component(ids: string[], edges: Edge[]) {
  const adjacency = new Map<string, string[]>();
  for (const current of edges) {
    adjacency.set(current.a, [...(adjacency.get(current.a) ?? []), current.b]);
    adjacency.set(current.b, [...(adjacency.get(current.b) ?? []), current.a]);
  }
  const seen = new Set<string>();
  let best: string[] = [];
  for (const id of ids) {
    if (seen.has(id)) continue;
    const queue = [id];
    const output: string[] = [];
    seen.add(id);
    while (queue.length) {
      const current = queue.shift()!;
      output.push(current);
      for (const next of adjacency.get(current) ?? []) {
        if (!seen.has(next)) {
          seen.add(next);
          queue.push(next);
        }
      }
    }
    output.sort();
    if (output.length > best.length || (output.length === best.length && output.join('\0') < best.join('\0'))) best = output;
  }
  return best;
}

function degree(id: string, edges: Edge[]) {
  return edges
    .filter(current => current.a === id || current.b === id)
    .reduce((sum, current) => sum + current.q / Math.max(0.02, current.sigma ** 2), 0);
}

// Deliberately JS-safe 32-bit FNV-1a. Rust uses the same record and confines the
// published revision to u32 so Android/JSON and native nodes compare it exactly.
function hashEdges(edges: Edge[]) {
  let hash = 2166136261 >>> 0;
  for (const current of edges) {
    const record = `${current.id}:${current.d.toFixed(3)}:${current.sigma.toFixed(3)}:${current.latest};`;
    for (const char of record) {
      hash ^= char.charCodeAt(0);
      hash = Math.imul(hash, 16777619) >>> 0;
    }
  }
  return hash;
}

function initializePositions(componentIds: string[], edges: Edge[], anchor: string, axis: string) {
  const ab = edge(edges, anchor, axis);
  if (!ab) return null;
  const positions = new Map<string, { x: number; y: number }>([
    [anchor, { x: 0, y: 0 }],
    [axis, { x: ab.d, y: 0 }],
  ]);
  let third: { id: string; x: number; y: number; leverage: number } | null = null;
  for (const id of componentIds.filter(candidate => candidate !== anchor && candidate !== axis)) {
    const ac = edge(edges, anchor, id);
    const bc = edge(edges, axis, id);
    if (!ac || !bc) continue;
    const x = (ac.d ** 2 + ab.d ** 2 - bc.d ** 2) / (2 * Math.max(1e-6, ab.d));
    const ySquared = ac.d ** 2 - x ** 2;
    if (ySquared <= 0) continue;
    const y = Math.sqrt(ySquared);
    const leverage = y / Math.max(ac.d, bc.d, ab.d, 0.1);
    if (!third || leverage > third.leverage) third = { id, x, y, leverage };
  }
  if (!third || third.leverage < 0.06) return null;
  positions.set(third.id, { x: third.x, y: third.y });

  let progress = true;
  while (progress) {
    progress = false;
    for (const id of componentIds) {
      if (positions.has(id)) continue;
      const neighbors = [...positions.keys()]
        .map(known => ({ known, measurement: edge(edges, id, known) }))
        .filter(value => value.measurement) as { known: string; measurement: Edge }[];
      if (neighbors.length < 2) continue;
      const firstPosition = positions.get(neighbors[0].known)!;
      let best: { x: number; y: number; score: number } | null = null;
      for (const second of neighbors.slice(1)) {
        const secondPosition = positions.get(second.known)!;
        const dx = secondPosition.x - firstPosition.x;
        const dy = secondPosition.y - firstPosition.y;
        const baseline = Math.hypot(dx, dy);
        if (baseline < 0.05) continue;
        const along =
          (neighbors[0].measurement.d ** 2 + baseline ** 2 - second.measurement.d ** 2) /
          (2 * baseline);
        const heightSquared = neighbors[0].measurement.d ** 2 - along ** 2;
        if (heightSquared < 0) continue;
        const height = Math.sqrt(heightSquared);
        const ux = dx / baseline;
        const uy = dy / baseline;
        for (const sign of [1, -1]) {
          const x = firstPosition.x + along * ux - sign * height * uy;
          const y = firstPosition.y + along * uy + sign * height * ux;
          const score = neighbors.reduce((sum, neighbor) => {
            const known = positions.get(neighbor.known)!;
            return sum + Math.abs(Math.hypot(x - known.x, y - known.y) - neighbor.measurement.d) / Math.max(0.15, neighbor.measurement.sigma);
          }, 0);
          if (!best || score < best.score) best = { x, y, score };
        }
      }
      if (best) {
        positions.set(id, { x: best.x, y: best.y });
        progress = true;
      }
    }
  }
  return { positions, thirdId: third.id };
}

function optimize(
  positions: Map<string, { x: number; y: number }>,
  edges: Edge[],
  anchor: string,
  axis: string,
  thirdId: string,
) {
  for (let iteration = 0; iteration < 180; iteration++) {
    const deltas = new Map<string, { x: number; y: number; count: number }>();
    let maxStep = 0;
    for (const current of edges) {
      const a = positions.get(current.a);
      const b = positions.get(current.b);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const predicted = Math.max(1e-6, Math.hypot(dx, dy));
      const residual = predicted - current.d;
      const limit = 2 * Math.max(0.25, current.sigma);
      const robust = Math.max(-limit, Math.min(limit, residual));
      const strength = Math.min(20, Math.max(0.02, current.q / Math.max(0.04, current.sigma ** 2)));
      const correction = robust * (0.2 * strength / (1 + strength));
      const ux = dx / predicted;
      const uy = dy / predicted;
      const aFixed = current.a === anchor || current.a === axis;
      const bFixed = current.b === anchor || current.b === axis;
      const share = aFixed || bFixed ? 1 : 0.5;
      for (const [id, sign, fixed] of [
        [current.a, 1, aFixed],
        [current.b, -1, bFixed],
      ] as [string, number, boolean][]) {
        if (fixed) continue;
        const value = deltas.get(id) ?? { x: 0, y: 0, count: 0 };
        value.x += sign * correction * ux * share;
        value.y += sign * correction * uy * share;
        value.count++;
        deltas.set(id, value);
      }
    }
    for (const [id, delta] of deltas) {
      const position = positions.get(id)!;
      const dx = delta.x / delta.count;
      const dy = delta.y / delta.count;
      position.x += dx;
      position.y += dy;
      maxStep = Math.max(maxStep, Math.hypot(dx, dy));
    }
    const third = positions.get(thirdId);
    if (third) third.y = Math.abs(third.y);
    if (maxStep < 1e-5) break;
  }
}

export function solveGeometry(inputNodes: Advertisement[]): GeometrySolution | null {
  if (!inputNodes.length) return null;
  const rejected: Rejected = [];
  const nodes = activeNodes(inputNodes, rejected);
  if (!nodes.length) return null;
  const ids = [...new Set(nodes.map(node => node.node_id))].sort();
  const allEdges = collectEdges(nodes, rejected);
  const connected = component(ids, allEdges);
  const connectedSet = new Set(connected);
  let edges = allEdges.filter(current => connectedSet.has(current.a) && connectedSet.has(current.b));
  const anchor = (connected.length ? connected : ids)
    .slice()
    .sort((a, b) => degree(b, edges) - degree(a, edges) || a.localeCompare(b))[0];
  const generated = Math.max(...nodes.map(node => node.monotonic_ns ?? 0));
  const base = {
    frame_id: `bf2-${anchor}`,
    revision: hashEdges(edges),
    generated_monotonic_ns: generated,
    anchor_node_id: anchor,
    rejected_edges: rejected,
  };

  if (connected.length < 2 || !edges.length) {
    const temporal = rejected.some(item => /stale|replayed|timestamp/.test(item.reason));
    return {
      ...base,
      dimension: 'UNKNOWN',
      state: temporal ? 'GEOMETRY_STALE' : 'GEOMETRY_INSUFFICIENT',
      axis_node_id: null,
      positions: [],
      residual_rms_m: null,
      condition_score: null,
      used_edges: [],
      reason: temporal
        ? 'All available pairwise range constraints are stale/replayed/temporally invalid'
        : 'No defensible inter-node distance edge yet',
    };
  }

  const axis = connected
    .filter(id => id !== anchor && edge(edges, anchor, id))
    .sort((a, b) => {
      const edgeA = edge(edges, anchor, a)!;
      const edgeB = edge(edges, anchor, b)!;
      return edgeB.q / edgeB.sigma ** 2 - edgeA.q / edgeA.sigma ** 2 || a.localeCompare(b);
    })[0];
  const ab = edge(edges, anchor, axis)!;
  const variance = ab.sigma ** 2;
  const axisPositions: GeometryPosition[] = [anchor, axis].map((id, index) => ({
    node_id: id,
    x_m: index ? ab.d : 0,
    y_m: 0,
    z_m: 0,
    error_radius_95_m: 2.4477 * ab.sigma,
    covariance_2x2: [[variance, 0], [0, variance]],
  }));

  if (connected.length < 3 || edges.length < 2 * connected.length - 3) {
    return {
      ...base,
      frame_id: `bf2-${anchor}-${axis}`,
      dimension: '1D',
      state: 'GEOMETRY_1D',
      axis_node_id: axis,
      positions: axisPositions,
      residual_rms_m: 0,
      condition_score: 0,
      used_edges: [ab.id],
      reason: 'Only a 1D baseline is observable; more independent range edges are required for 2D',
    };
  }

  const initialized = initializePositions(connected, edges, anchor, axis);
  if (!initialized) {
    return {
      ...base,
      frame_id: `bf2-${anchor}-${axis}`,
      dimension: '1D',
      state: 'GEOMETRY_INSUFFICIENT',
      axis_node_id: axis,
      positions: axisPositions,
      residual_rms_m: null,
      condition_score: 0,
      used_edges: [ab.id],
      reason: 'Range graph is degenerate or nearly collinear; refusing to manufacture a 2D layout',
    };
  }

  const positions = initialized.positions;
  optimize(positions, edges, anchor, axis, initialized.thirdId);

  const kept: Edge[] = [];
  for (const current of edges) {
    const a = positions.get(current.a);
    const b = positions.get(current.b);
    if (!a || !b) continue;
    const residual = Math.abs(Math.hypot(a.x - b.x, a.y - b.y) - current.d);
    const threshold = Math.max(3 * current.sigma, 1, 0.35 * current.d);
    if (residual > threshold) {
      rejected.push({ edge_id: current.id, reason: 'persistent solver outlier', residual_m: residual });
    } else {
      kept.push(current);
    }
  }
  if (kept.length >= 2 * positions.size - 3 && kept.length < edges.length) {
    edges = kept;
    optimize(positions, edges, anchor, axis, initialized.thirdId);
  }

  const residuals = edges.flatMap(current => {
    const a = positions.get(current.a);
    const b = positions.get(current.b);
    return a && b ? [Math.hypot(a.x - b.x, a.y - b.y) - current.d] : [];
  });
  const rms = residuals.length
    ? Math.sqrt(residuals.reduce((sum, residual) => sum + residual * residual, 0) / residuals.length)
    : 0;
  const values = [...positions.values()];
  let span = 0.1;
  let cross = 0;
  for (let i = 0; i < values.length; i++) {
    for (let j = i + 1; j < values.length; j++) {
      span = Math.max(span, Math.hypot(values[i].x - values[j].x, values[i].y - values[j].y));
      for (let k = j + 1; k < values.length; k++) {
        cross = Math.max(
          cross,
          Math.abs(
            (values[j].x - values[i].x) * (values[k].y - values[i].y) -
              (values[j].y - values[i].y) * (values[k].x - values[i].x),
          ),
        );
      }
    }
  }
  const condition = Math.max(0, Math.min(1, cross / (span * span) / 0.35));
  const disconnected = positions.size < ids.length;
  const degraded = disconnected || condition < 0.18 || rms > 2.5;
  const outputPositions = [...positions]
    .map(([id, position]) => {
      const information = edges
        .filter(current => current.a === id || current.b === id)
        .reduce((sum, current) => sum + current.q / Math.max(0.04, current.sigma ** 2), 0);
      const sigma = Math.max(0.15, Math.sqrt(1 / Math.max(0.05, information))) + rms * 0.5 + (1 - condition) * 0.5;
      return {
        node_id: id,
        x_m: position.x,
        y_m: position.y,
        z_m: 0,
        error_radius_95_m: 2.4477 * sigma,
        covariance_2x2: [[sigma ** 2, 0], [0, sigma ** 2]] as [[number, number], [number, number]],
      };
    })
    .sort((a, b) => a.node_id.localeCompare(b.node_id));

  return {
    ...base,
    frame_id: `bf2-${anchor}-${axis}`,
    revision: hashEdges(edges),
    dimension: '2D',
    state: degraded ? 'GEOMETRY_DEGRADED' : 'GEOMETRY_2D',
    axis_node_id: axis,
    positions: outputPositions,
    residual_rms_m: rms,
    condition_score: condition,
    used_edges: edges.map(current => current.id),
    reason: disconnected
      ? `Solved ${positions.size}/${ids.length} active nodes; unresolved nodes are not drawn`
      : condition < 0.18
        ? 'Geometry is poorly conditioned / nearly collinear'
        : rms > 2.5
          ? 'Range residuals exceed the reliable geometry threshold'
          : null,
  };
}

export function chooseCoordinatorGeometry(
  nodes: Advertisement[],
  coordinatorNodeId: string | null,
  localNodeId: string | null,
  localSolution: GeometrySolution | null,
): GeometrySelection {
  if (coordinatorNodeId && coordinatorNodeId === localNodeId) {
    return { solution: localSolution, source: 'LOCAL_ELECTED_COORDINATOR' };
  }
  const coordinator = coordinatorNodeId
    ? nodes.find(node => node.node_id === coordinatorNodeId)
    : undefined;
  if (
    coordinator &&
    coordinator.geometry_publisher_node_id === coordinatorNodeId &&
    coordinator.published_geometry &&
    coordinator.published_geometry.frame_id
  ) {
    return {
      solution: coordinator.published_geometry,
      source: 'ELECTED_COORDINATOR_PUBLICATION',
    };
  }
  return {
    solution: localSolution,
    source: 'LOCAL_DETERMINISTIC_FALLBACK_AWAITING_COORDINATOR_PUBLICATION',
  };
}

export function estimateHuman(nodes: Advertisement[], geometry: GeometrySolution | null): HumanEstimate | null {
  if (!geometry || geometry.dimension !== '2D' || geometry.state === 'GEOMETRY_INSUFFICIENT' || geometry.state === 'GEOMETRY_STALE') return null;
  const positionMap = new Map(geometry.positions.map(position => [position.node_id, position]));
  const usable = nodes.flatMap(node => {
    const position = positionMap.get(node.node_id);
    if (!node.scanning || !position || node.rssi_dbm == null || node.baseline_rssi_dbm == null) return [];
    const anomaly = Math.min(20, Math.abs(node.rssi_dbm - node.baseline_rssi_dbm) / Math.max(1, node.baseline_sigma_db ?? 2));
    return anomaly >= 0.75 ? [{ node, position, anomaly, weight: Math.max(0.1, anomaly - 0.5) }] : [];
  });
  if (usable.length < 3) return null;
  const sumWeight = usable.reduce((sum, value) => sum + value.weight, 0);
  const x = usable.reduce((sum, value) => sum + value.position.x_m * value.weight, 0) / sumWeight;
  const y = usable.reduce((sum, value) => sum + value.position.y_m * value.weight, 0) / sumWeight;
  const varianceX = usable.reduce(
    (sum, value) => sum + value.weight * ((value.position.x_m - x) ** 2 + value.position.covariance_2x2[0][0]),
    0,
  ) / sumWeight;
  const varianceY = usable.reduce(
    (sum, value) => sum + value.weight * ((value.position.y_m - y) ** 2 + value.position.covariance_2x2[1][1]),
    0,
  ) / sumWeight;
  const penalty = (geometry.residual_rms_m ?? 1) + 1.5 * (1 - (geometry.condition_score ?? 0));
  const error = Math.max(1, 2.4477 * (Math.sqrt(varianceX + varianceY) + 0.5 * penalty));
  const range = Math.hypot(x, y);
  const uncertainty = Math.max(0, Math.min(100, 100 * error / Math.max(2, range)));
  const meanAnomaly = usable.reduce((sum, value) => sum + value.anomaly, 0) / usable.length;
  const confidence = Math.max(0, Math.min(0.95, 1 - Math.exp(-0.35 * Math.max(0, meanAnomaly - 0.75))));
  return {
    x_m: x,
    y_m: y,
    range_m: range,
    bearing_deg: Math.atan2(x, y) * 180 / Math.PI,
    human_confidence: confidence,
    uncertainty_percent: uncertainty,
    error_radius_95_m: error,
    quality: uncertainty <= 20 ? 'HIGH' : uncertainty <= 40 ? 'MEDIUM' : uncertainty <= 70 ? 'LOW' : 'VERY_LOW',
    method: 'EXPERIMENTAL_RSSI_DISTURBANCE_AUTOGEOMETRY_V2',
    state: meanAnomaly >= 5 ? 'PROBABLE_HUMAN' : 'POSSIBLE_HUMAN',
  };
}
