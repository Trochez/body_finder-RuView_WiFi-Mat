import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  SafeAreaView,
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  Share,
  Platform,
  PermissionsAndroid,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import BodyFinderNative from './modules/body-finder-native';
import {
  Advertisement,
  GeometryPosition,
  HumanEstimate,
  chooseCoordinatorGeometry,
  estimateHuman,
  solveGeometry,
} from './src/autogeometry';
import { diagnoseGeometryGraph } from './src/geometryDiagnostics';

const T = {
  en: {
    title: 'Body Finder – RuView',
    experimental: 'EXPERIMENTAL RF / AUTO GEOMETRY — NOT VALIDATED FOR RESCUE USE',
    radar: 'Radar',
    expert: 'Expert',
    calibrate: 'Calibrate empty scene',
    scanning: 'Start scan',
    stop: 'Stop scan',
    peers: 'nodes',
    share: 'Share complete test JSON',
    empty: 'Keep the target area empty while calibrating.',
    network: 'OPEN / UNTRUSTED FIELD NETWORK',
    relative: 'POSITION RELATIVE TO THIS DEVICE',
    geometry: 'SENSOR GEOMETRY',
    estimating: 'Estimating automatically…',
    positioned: 'nodes positioned',
    residual: 'residual',
    condition: 'condition',
    noTarget: 'No defensible human position yet. Automatic 2D sensor geometry + ≥3 calibrated scanning nodes with measurable RF disturbance are required.',
    confidence: 'human confidence',
    uncertainty: 'position uncertainty',
    evidence: 'Evidence: commodity connected-Wi-Fi RSSI disturbance (not CSI). Sensor coordinates come only from pairwise ranging.',
    unresolved: 'unresolved nodes are intentionally not placed on the radar',
  },
  es: {
    title: 'Body Finder – RuView',
    experimental: 'RF / GEOMETRÍA AUTOMÁTICA EXPERIMENTAL — NO VALIDADO PARA RESCATE',
    radar: 'Radar',
    expert: 'Experto',
    calibrate: 'Calibrar escena vacía',
    scanning: 'Iniciar escaneo',
    stop: 'Detener escaneo',
    peers: 'nodos',
    share: 'Compartir JSON completo de prueba',
    empty: 'Mantén vacía el área objetivo durante la calibración.',
    network: 'RED DE CAMPO ABIERTA / NO CONFIABLE',
    relative: 'POSICIÓN RELATIVA A ESTE DISPOSITIVO',
    geometry: 'GEOMETRÍA DE SENSORES',
    estimating: 'Estimando automáticamente…',
    positioned: 'nodos posicionados',
    residual: 'residual',
    condition: 'condición',
    noTarget: 'Aún no hay posición humana defendible. Se requiere geometría automática 2D + ≥3 nodos calibrados y escaneando con perturbación RF medible.',
    confidence: 'confianza humana',
    uncertainty: 'incertidumbre de posición',
    evidence: 'Evidencia: perturbación RSSI de Wi‑Fi conectado (no CSI). Las coordenadas de sensores provienen únicamente del ranging entre nodos.',
    unresolved: 'los nodos no resueltos no se colocan artificialmente en el radar',
  },
};

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

type VisualPosition = { x_m: number; y_m: number };

async function requestAndroidPermissions() {
  if (Platform.OS !== 'android') return;
  const permissions: any[] = [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
  const api = Number(Platform.Version);
  if (api >= 31) {
    permissions.push(
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_ADVERTISE,
    );
  }
  if (api >= 33) permissions.push(PermissionsAndroid.PERMISSIONS.NEARBY_WIFI_DEVICES);
  if (api >= 36) permissions.push('android.permission.RANGING' as any);
  try {
    await PermissionsAndroid.requestMultiple(permissions);
  } catch {
    // Capability probes report denied/missing permissions truthfully in the UI.
  }
}

function relativePosition(position: GeometryPosition, origin: GeometryPosition) {
  return { x_m: position.x_m - origin.x_m, y_m: position.y_m - origin.y_m };
}

function relativeVisualPosition(position: VisualPosition, origin: VisualPosition) {
  return { x_m: position.x_m - origin.x_m, y_m: position.y_m - origin.y_m };
}

function relativeTarget(target: HumanEstimate | null, origin: GeometryPosition | undefined): HumanEstimate | null {
  if (!target || !origin) return null;
  const x = target.x_m - origin.x_m;
  const y = target.y_m - origin.y_m;
  const range = Math.hypot(x, y);
  const uncertainty = Math.max(0, Math.min(100, 100 * target.error_radius_95_m / Math.max(2, range)));
  return {
    ...target,
    x_m: x,
    y_m: y,
    range_m: range,
    bearing_deg: Math.atan2(x, y) * 180 / Math.PI,
    uncertainty_percent: uncertainty,
    quality: uncertainty <= 20 ? 'HIGH' : uncertainty <= 40 ? 'MEDIUM' : uncertainty <= 70 ? 'LOW' : 'VERY_LOW',
  };
}

export default function App() {
  const [lang, setLang] = useState<'en' | 'es'>('es');
  const [mode, setMode] = useState<'radar' | 'expert'>('radar');
  const [caps, setCaps] = useState<any>({});
  const [local, setLocal] = useState<Advertisement | null>(null);
  const [peers, setPeers] = useState<Advertisement[]>([]);
  const [baseline, setBaseline] = useState<number | null>(null);
  const [sigma, setSigma] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [calibrating, setCalibrating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visualPositions, setVisualPositions] = useState<Record<string, VisualPosition>>({});
  const visualFrame = useRef<string | null>(null);
  const tx = T[lang];

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        await requestAndroidPermissions();
        setCaps(JSON.parse(BodyFinderNative.getCapabilitiesJson()));
        await BodyFinderNative.startFabric(null, null, 'body-finder-lab');
      } catch (cause: any) {
        if (live) setError(String(cause?.message ?? cause));
      }
    })();
    const timer = setInterval(() => {
      if (!live) return;
      try {
        const localAdvertisement = JSON.parse(BodyFinderNative.getLocalAdvertisementJson());
        setLocal(localAdvertisement?.node_id ? localAdvertisement : null);
        setPeers(JSON.parse(BodyFinderNative.getPeersJson()) as Advertisement[]);
        setCaps(JSON.parse(BodyFinderNative.getCapabilitiesJson()));
      } catch (cause: any) {
        setError(String(cause?.message ?? cause));
      }
    }, 800);
    return () => {
      live = false;
      clearInterval(timer);
      try { BodyFinderNative.stopFabric(); } catch {}
    };
  }, []);

  useEffect(() => {
    try { BodyFinderNative.updateLocalState(baseline, sigma, scanning); } catch {}
  }, [baseline, sigma, scanning]);

  const nodes = useMemo(() => (local ? [local, ...peers] : peers), [local, peers]);
  const coordinator = useMemo(
    () => nodes
      .filter(node => node.protocol_version === 2)
      .slice()
      .sort((a, b) => b.coordinator_score - a.coordinator_score || a.node_id.localeCompare(b.node_id))[0]?.node_id ?? null,
    [nodes],
  );
  const computedGeometry = useMemo(() => solveGeometry(nodes), [nodes]);
  const geometrySelection = useMemo(
    () => chooseCoordinatorGeometry(nodes, coordinator, local?.node_id ?? null, computedGeometry),
    [nodes, coordinator, local?.node_id, computedGeometry],
  );
  const geometry = geometrySelection.solution;
  const graphDiagnostics = useMemo(() => diagnoseGeometryGraph(nodes), [nodes]);

  useEffect(() => {
    const elected = Boolean(local?.node_id && coordinator === local.node_id);
    try {
      BodyFinderNative.updatePublishedGeometry(
        elected,
        elected && computedGeometry ? JSON.stringify(computedGeometry) : null,
      );
    } catch {}
  }, [local?.node_id, coordinator, computedGeometry]);

  // Display-only hysteresis. The authoritative geometry/export stays untouched;
  // the radar eases small same-frame revisions and resets immediately on reframe.
  useEffect(() => {
    if (!geometry) {
      visualFrame.current = null;
      setVisualPositions({});
      return;
    }
    const sameFrame = visualFrame.current === geometry.frame_id;
    setVisualPositions(previous => {
      const next: Record<string, VisualPosition> = {};
      for (const position of geometry.positions) {
        const old = sameFrame ? previous[position.node_id] : undefined;
        const alpha = old ? 0.35 : 1;
        next[position.node_id] = {
          x_m: old ? old.x_m + alpha * (position.x_m - old.x_m) : position.x_m,
          y_m: old ? old.y_m + alpha * (position.y_m - old.y_m) : position.y_m,
        };
      }
      return next;
    });
    visualFrame.current = geometry.frame_id;
  }, [geometry]);

  const arrayTarget = useMemo(() => estimateHuman(nodes, geometry), [nodes, geometry]);
  const localGeometry = useMemo(
    () => geometry?.positions.find(position => position.node_id === local?.node_id),
    [geometry, local?.node_id],
  );
  const target = useMemo(() => relativeTarget(arrayTarget, localGeometry), [arrayTarget, localGeometry]);
  const rangeCount = nodes.reduce((count, node) => count + (node.ranges?.length ?? 0), 0);
  const unresolved = Math.max(0, nodes.length - (geometry?.positions.length ?? 0));
  const visualLocal = local?.node_id ? visualPositions[local.node_id] : undefined;

  async function calibrate() {
    setCalibrating(true);
    setScanning(false);
    setError(null);
    const samples: number[] = [];
    try {
      for (let i = 0; i < 32; i++) {
        const rssi = BodyFinderNative.getWifiRssi();
        if (typeof rssi === 'number') samples.push(rssi);
        await sleep(250);
      }
      if (samples.length < 8) {
        throw new Error(lang === 'es'
          ? 'No hay suficientes muestras RSSI Wi‑Fi reales. Conecta Wi‑Fi y concede permisos.'
          : 'Not enough live Wi-Fi RSSI samples. Connect Wi-Fi and grant permissions.');
      }
      const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
      const standardDeviation = Math.max(
        1,
        Math.sqrt(samples.reduce((sum, value) => sum + (value - mean) ** 2, 0) / samples.length),
      );
      setBaseline(mean);
      setSigma(standardDeviation);
    } catch (cause: any) {
      setError(String(cause?.message ?? cause));
    } finally {
      setCalibrating(false);
    }
  }

  async function share() {
    const payload = {
      report_version: 5,
      generated_at: new Date().toISOString(),
      app: 'Body Finder – RuView',
      build: '0.2.0-experimental.3',
      protocol_version: 2,
      truth: 'LIVE_DEVICE_CAPABILITIES__REAL_PAIRWISE_RANGING_WHEN_REPORTED__COORDINATOR_GEOMETRY_PUBLICATION__AUTOGEOMETRY_EXPERIMENTAL_NOT_RESCUE_VALIDATED',
      manual_geometry_override: false,
      node_id: local?.node_id ?? null,
      capabilities: caps,
      local,
      peers,
      coordinator_node_id: coordinator,
      geometry_source: geometrySelection.source,
      geometry,
      locally_computed_geometry: computedGeometry,
      graph_diagnostics: graphDiagnostics,
      range_observations: nodes.flatMap(node => node.ranges ?? []),
      estimate_array_frame: arrayTarget,
      estimate_relative_to_this_device: target,
      instructions: 'Return this JSON with native JSONL logs, screenshots and external ground truth. Never feed ground-truth node coordinates into the app.',
    };
    await Share.share({
      message: JSON.stringify(payload, null, 2),
      title: 'Body Finder automatic-geometry field result',
    });
  }

  const scale = 18;
  const geometryState = geometry?.state ?? 'GEOMETRY_INSUFFICIENT';
  return (
    <SafeAreaView style={s.safe}>
      <StatusBar style="light" />
      <View style={s.header}>
        <View style={s.headerText}>
          <Text style={s.title}>{tx.title}</Text>
          <Text style={s.warn}>{tx.experimental}</Text>
        </View>
        <Pressable onPress={() => setLang(lang === 'en' ? 'es' : 'en')}>
          <Text style={s.link}>{lang.toUpperCase()}</Text>
        </Pressable>
      </View>
      <View style={s.tabs}>
        <Pressable style={[s.tab, mode === 'radar' && s.tabOn]} onPress={() => setMode('radar')}>
          <Text style={s.tabText}>{tx.radar}</Text>
        </Pressable>
        <Pressable style={[s.tab, mode === 'expert' && s.tabOn]} onPress={() => setMode('expert')}>
          <Text style={s.tabText}>{tx.expert}</Text>
        </Pressable>
      </View>
      {mode === 'radar' ? (
        <ScrollView contentContainerStyle={s.body}>
          <View style={s.statusRow}>
            <Text style={s.pill}>{nodes.length} {tx.peers}</Text>
            <Text style={s.pill}>{rangeCount} RANGE</Text>
            <Text style={s.pill}>COORD {coordinator?.slice(-8) ?? '—'}</Text>
          </View>
          <Text style={s.network}>{tx.network}</Text>
          <View style={s.card}>
            <Text style={s.h2}>{tx.geometry}</Text>
            <Text style={s.geometryState}>{geometryState.replaceAll('_', ' ')}</Text>
            <Text style={s.text}>{geometry?.positions.length ?? 0}/{nodes.length} {tx.positioned} · {geometry?.dimension ?? 'UNKNOWN'} AUTO</Text>
            <Text style={s.text}>{tx.residual}: {geometry?.residual_rms_m != null ? `${geometry.residual_rms_m.toFixed(2)} m` : '—'} · {tx.condition}: {geometry?.condition_score != null ? `${(100 * geometry.condition_score).toFixed(0)}%` : '—'}</Text>
            <Text style={s.text}>revision: {geometry?.revision ?? '—'} · source: {geometrySelection.source}</Text>
            <Text style={s.muted}>{geometry?.reason ?? tx.estimating}</Text>
            {unresolved > 0 && <Text style={s.muted}>{unresolved} {tx.unresolved}</Text>}
          </View>
          <Text style={s.relative}>{tx.relative}</Text>
          <View style={s.radar}>
            {[90, 180, 270].map(diameter => (
              <View key={diameter} style={[s.ring, { width: diameter, height: diameter, borderRadius: diameter / 2, left: 150 - diameter / 2, top: 150 - diameter / 2 }]} />
            ))}
            <View style={s.operator} />
            {visualLocal && geometry?.positions
              .filter(position => position.node_id !== local?.node_id && visualPositions[position.node_id])
              .map((position, index) => {
                const relative = relativeVisualPosition(visualPositions[position.node_id], visualLocal);
                const diameter = Math.min(90, Math.max(10, position.error_radius_95_m * scale * 2));
                return (
                  <React.Fragment key={position.node_id}>
                    <View style={[s.sensorUncertainty, {
                      width: diameter,
                      height: diameter,
                      borderRadius: diameter / 2,
                      left: 150 + relative.x_m * scale - diameter / 2,
                      top: 150 - relative.y_m * scale - diameter / 2,
                    }]} />
                    <View style={[s.sensor, { left: 144 + relative.x_m * scale, top: 144 - relative.y_m * scale }]}>
                      <Text style={s.dotLabel}>{index + 1}</Text>
                    </View>
                  </React.Fragment>
                );
              })}
            {target && (
              <>
                <View style={[s.targetRing, {
                  width: Math.min(260, target.error_radius_95_m * 36),
                  height: Math.min(260, target.error_radius_95_m * 36),
                  borderRadius: 130,
                  left: 150 - Math.min(260, target.error_radius_95_m * 36) / 2 + target.x_m * scale,
                  top: 150 - Math.min(260, target.error_radius_95_m * 36) / 2 - target.y_m * scale,
                }]} />
                <View style={[s.target, { left: 144 + target.x_m * scale, top: 144 - target.y_m * scale }]} />
              </>
            )}
          </View>
          {target ? (
            <View style={s.card}>
              <Text style={s.h2}>{target.state.replace('_', ' ')}</Text>
              <Text style={s.big}>{target.range_m.toFixed(1)} m · {target.bearing_deg.toFixed(0)}°</Text>
              <Text style={s.text}>x {target.x_m.toFixed(2)} m · y {target.y_m.toFixed(2)} m</Text>
              <Text style={s.text}>{tx.confidence}: {(target.human_confidence * 100).toFixed(0)}%</Text>
              <Text style={s.text}>{tx.uncertainty}: {target.uncertainty_percent.toFixed(0)}% · ±{target.error_radius_95_m.toFixed(1)} m (95%)</Text>
              <Text style={s.text}>quality: {target.quality}</Text>
              <Text style={s.muted}>{tx.evidence}</Text>
            </View>
          ) : (
            <View style={s.card}><Text style={s.text}>{tx.noTarget}</Text></View>
          )}
          <Text style={s.muted}>{tx.empty}</Text>
          <Pressable disabled={calibrating} style={s.btn} onPress={calibrate}>
            <Text style={s.btnText}>{calibrating ? 'CALIBRATING…' : tx.calibrate}</Text>
          </Pressable>
          <Pressable disabled={baseline == null} style={[s.btn, baseline == null && s.disabled]} onPress={() => setScanning(value => !value)}>
            <Text style={s.btnText}>{scanning ? tx.stop : tx.scanning}</Text>
          </Pressable>
          <Pressable style={s.btnAlt} onPress={share}><Text style={s.btnText}>{tx.share}</Text></Pressable>
          {error && <Text style={s.err}>{error}</Text>}
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={s.body}>
          <View style={s.card}>
            <Text style={s.h2}>Truth / source classification</Text>
            <Text style={s.text}>Node geometry: AUTO ONLY — manual override disabled</Text>
            <Text style={s.text}>Geometry authority: {geometrySelection.source}</Text>
            <Text style={s.text}>Pairwise range: live native measurement when present; every edge exposes technology/sigma/source/age</Text>
            <Text style={s.text}>Connected Wi‑Fi RSSI: human-presence experiment only; never used as phone-to-phone distance</Text>
            <Text style={s.text}>CSI: UNSUPPORTED unless a future verified adapter is loaded</Text>
          </View>
          {[
            ['Geometry solution', geometry],
            ['Locally computed geometry', computedGeometry],
            ['Graph diagnostics / sample age', graphDiagnostics],
            ['Range observations', nodes.flatMap(node => node.ranges ?? [])],
            ['Capabilities', caps],
            ['Local node', local],
            ['Peers', peers],
            ['Array-frame estimate', arrayTarget],
            ['Relative estimate', target],
          ].map(([name, value]) => (
            <View style={s.card} key={String(name)}>
              <Text style={s.h2}>{String(name)}</Text>
              <Text selectable style={s.code}>{JSON.stringify(value, null, 2)}</Text>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#071016' },
  header: { padding: 16, paddingTop: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  headerText: { flex: 1, paddingRight: 8 },
  title: { color: '#e8f7ff', fontSize: 22, fontWeight: '800' },
  warn: { color: '#ffb35c', fontSize: 10, fontWeight: '700', marginTop: 3 },
  link: { color: '#66d7ff', fontWeight: '800', padding: 8 },
  tabs: { flexDirection: 'row', paddingHorizontal: 12, gap: 8 },
  tab: { flex: 1, padding: 10, borderRadius: 10, backgroundColor: '#0d1b24', alignItems: 'center' },
  tabOn: { backgroundColor: '#15384a' },
  tabText: { color: '#e6f6ff', fontWeight: '700' },
  body: { padding: 14, paddingBottom: 40, gap: 10 },
  statusRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  pill: { color: '#b7eaff', backgroundColor: '#102935', paddingHorizontal: 9, paddingVertical: 5, borderRadius: 99, fontSize: 11, fontWeight: '700' },
  network: { color: '#ffcb76', fontSize: 10, fontWeight: '700' },
  relative: { color: '#8edfff', fontSize: 11, fontWeight: '800', textAlign: 'center', marginTop: 2 },
  radar: { width: 300, height: 300, alignSelf: 'center', position: 'relative', overflow: 'hidden', borderRadius: 150, backgroundColor: '#081a22' },
  ring: { position: 'absolute', borderWidth: 1, borderColor: '#1d4556' },
  operator: { position: 'absolute', left: 144, top: 144, width: 12, height: 12, borderRadius: 6, backgroundColor: '#fff' },
  sensorUncertainty: { position: 'absolute', borderWidth: 1, borderColor: '#2f7390' },
  sensor: { position: 'absolute', width: 12, height: 12, borderRadius: 6, backgroundColor: '#58c8ff', alignItems: 'center', justifyContent: 'center' },
  dotLabel: { fontSize: 8, fontWeight: '900', color: '#001018' },
  target: { position: 'absolute', width: 12, height: 12, borderRadius: 6, backgroundColor: '#ff9d55' },
  targetRing: { position: 'absolute', borderWidth: 1, borderColor: '#ff9d55' },
  card: { backgroundColor: '#0d1b24', borderRadius: 14, padding: 13, gap: 4 },
  h2: { color: '#bfeeff', fontSize: 13, fontWeight: '800' },
  geometryState: { color: '#72e5a1', fontSize: 18, fontWeight: '900' },
  big: { color: '#fff', fontSize: 23, fontWeight: '800' },
  text: { color: '#dfedf3', fontSize: 13 },
  muted: { color: '#8198a4', fontSize: 11 },
  code: { color: '#b9d2dc', fontSize: 10, fontFamily: Platform.select({ android: 'monospace', ios: 'Menlo' }) },
  btn: { backgroundColor: '#16688b', padding: 13, borderRadius: 12, alignItems: 'center' },
  btnAlt: { backgroundColor: '#263845', padding: 13, borderRadius: 12, alignItems: 'center' },
  disabled: { opacity: 0.4 },
  btnText: { color: '#fff', fontWeight: '800' },
  err: { color: '#ff8a8a', fontSize: 12 },
});
