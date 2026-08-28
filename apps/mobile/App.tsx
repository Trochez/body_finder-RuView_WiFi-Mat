import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AppState,
  SafeAreaView,
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  Share,
  Platform,
  PermissionsAndroid,
  StatusBar as NativeStatusBar,
} from 'react-native';
import { StatusBar as ExpoStatusBar } from 'expo-status-bar';
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
import { applyReciprocalFusion } from './src/rangeFusion';
import { BUILD, REPORT_VERSION, HUMAN_SCANNING_ENABLED, RELEASE } from './src/version';
import { estimateHumanPresence, selectAuthoritativePresence } from './src/humanPresence';

const T = {
  en: {
    title: 'Body Finder – RuView',
    experimental: 'EXPERIMENTAL RF / AUTO GEOMETRY — NOT VALIDATED FOR RESCUE USE',
    radar: 'Radar', expert: 'Expert', calibrate: 'Calibrate empty scene', scanning: 'Start scan', stop: 'Stop scan',
    peers: 'nodes', share: 'Share complete test JSON', empty: 'Keep the target area empty while calibrating.',
    network: 'OPEN / UNTRUSTED FIELD NETWORK', relative: 'POSITION RELATIVE TO THIS DEVICE', geometry: 'SENSOR GEOMETRY',
    estimating: 'Estimating automatically…', positioned: 'nodes positioned', residual: 'solver residual', condition: 'graph condition',
    noTarget: 'Presence-only experimental mode. A negative RF result is not proof that no person is present. Localization remains blocked until dev-21 physical acceptance.',
    confidence: 'human confidence', uncertainty: 'position uncertainty',
    evidence: 'Evidence: connected-Wi-Fi RSSI disturbance (not CSI). Sensor metric coordinates require validated pairwise ranging.',
    unresolved: 'unresolved nodes are intentionally not placed on the radar', startRun: 'Start validation run', endRun: 'End validation run',
  },
  es: {
    title: 'Body Finder – RuView',
    experimental: 'RF / GEOMETRÍA AUTOMÁTICA EXPERIMENTAL — NO VALIDADO PARA RESCATE',
    radar: 'Radar', expert: 'Experto', calibrate: 'Calibrar escena vacía', scanning: 'Iniciar escaneo', stop: 'Detener escaneo',
    peers: 'nodos', share: 'Compartir JSON completo de prueba', empty: 'Mantén vacía el área objetivo durante la calibración.',
    network: 'RED DE CAMPO ABIERTA / NO CONFIABLE', relative: 'POSICIÓN RELATIVA A ESTE DISPOSITIVO', geometry: 'GEOMETRÍA DE SENSORES',
    estimating: 'Estimando automáticamente…', positioned: 'nodos posicionados', residual: 'residual del solver', condition: 'condición del grafo',
    noTarget: 'Modo experimental solo de presencia. Un resultado RF negativo no prueba ausencia de personas. La localización sigue bloqueada hasta la aceptación física dev-21.',
    confidence: 'confianza humana', uncertainty: 'incertidumbre de posición',
    evidence: 'Evidencia: perturbación RSSI de Wi‑Fi conectado (no CSI). Las coordenadas métricas requieren ranging entre nodos validado.',
    unresolved: 'los nodos no resueltos no se colocan artificialmente en el radar', startRun: 'Iniciar corrida de validación', endRun: 'Finalizar corrida de validación',
  },
};

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
type VisualPosition = { x_m: number; y_m: number };

async function requestAndroidPermissions() {
  if (Platform.OS !== 'android') return;
  const permissions: any[] = [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
  const api = Number(Platform.Version);
  if (api >= 31) permissions.push(
    PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
    PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
    PermissionsAndroid.PERMISSIONS.BLUETOOTH_ADVERTISE,
  );
  if (api >= 33) {
    permissions.push(PermissionsAndroid.PERMISSIONS.NEARBY_WIFI_DEVICES);
    permissions.push('android.permission.POST_NOTIFICATIONS' as any);
  }
  if (api >= 36) permissions.push('android.permission.RANGING' as any);
  try { await PermissionsAndroid.requestMultiple(permissions); } catch {}
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
  return { ...target, x_m: x, y_m: y, range_m: range, bearing_deg: Math.atan2(x, y) * 180 / Math.PI,
    uncertainty_percent: uncertainty, quality: uncertainty <= 20 ? 'HIGH' : uncertainty <= 40 ? 'MEDIUM' : uncertainty <= 70 ? 'LOW' : 'VERY_LOW' };
}

export default function App() {
  const [lang, setLang] = useState<'en' | 'es'>('es');
  const [mode, setMode] = useState<'radar' | 'expert'>('radar');
  const [caps, setCaps] = useState<any>({});
  const [diagnostics, setDiagnostics] = useState<any>({});
  const [local, setLocal] = useState<Advertisement | null>(null);
  const [peers, setPeers] = useState<Advertisement[]>([]);
  const [baseline, setBaseline] = useState<number | null>(null);
  const [sigma, setSigma] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [calibrating, setCalibrating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visualPositions, setVisualPositions] = useState<Record<string, VisualPosition>>({});
  const [validationRun, setValidationRun] = useState<any>(null);
  const [validationNotice, setValidationNotice] = useState<string | null>(null);
  const validationActionLock = useRef(false);
  const exportSequenceByRun = useRef<Record<string, number>>({});
  const visualFrame = useRef<string | null>(null);
  const tx = T[lang];

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        await requestAndroidPermissions();
        setCaps(JSON.parse(BodyFinderNative.getCapabilitiesJson()));
        await BodyFinderNative.startFabric(null, null, 'body-finder-lab');
        try { BodyFinderNative.updateAppVisibility(AppState.currentState); } catch {}
      } catch (cause: any) { if (live) setError(String(cause?.message ?? cause)); }
    })();
    const appStateSubscription = AppState.addEventListener('change', state => {
      try { BodyFinderNative.updateAppVisibility(state); } catch {}
      if (state !== 'active') setValidationNotice(lang === 'es' ? 'La app salió de primer plano; el JSON registrará el intervalo y su contexto.' : 'The app left foreground; JSON will record the interval and its context.');
    });
    const timer = setInterval(() => {
      if (!live) return;
      try {
        const localAdvertisement = JSON.parse(BodyFinderNative.getLocalAdvertisementJson());
        setLocal(localAdvertisement?.node_id ? localAdvertisement : null);
        setPeers(JSON.parse(BodyFinderNative.getPeersJson()) as Advertisement[]);
        setCaps(JSON.parse(BodyFinderNative.getCapabilitiesJson()));
        const fresh = JSON.parse(BodyFinderNative.getDiagnosticsJson());
        setDiagnostics(fresh);
        setValidationRun(fresh?.validation_run ?? null);
      } catch (cause: any) { setError(String(cause?.message ?? cause)); }
    }, 800);
    return () => {
      live = false;
      clearInterval(timer);
      appStateSubscription.remove();
      try { BodyFinderNative.stopFabric(); } catch {}
    };
  }, []);

  useEffect(() => { try { BodyFinderNative.updateLocalState(baseline, sigma, scanning); } catch {} }, [baseline, sigma, scanning]);

  const nodes = useMemo(() => (local ? [local, ...peers] : peers), [local, peers]);
  const fused = useMemo(() => applyReciprocalFusion(nodes), [nodes]);
  const geometryNodes = fused.nodes;
  const coordinator = useMemo(() => nodes.filter(node => node.protocol_version === 2).slice()
    .sort((a, b) => b.coordinator_score - a.coordinator_score || a.node_id.localeCompare(b.node_id))[0]?.node_id ?? null, [nodes]);
  const computedGeometry = useMemo(() => solveGeometry(geometryNodes), [geometryNodes]);
  const localPresenceDiagnostic = useMemo(() => estimateHumanPresence(nodes, coordinator === local?.node_id ? 'coordinator' : 'diagnostic'), [nodes, coordinator, local?.node_id]);
  const presence = useMemo(() => selectAuthoritativePresence(nodes, coordinator, local?.node_id ?? null, localPresenceDiagnostic), [nodes, coordinator, local?.node_id, localPresenceDiagnostic]);
  const geometrySelection = useMemo(() => chooseCoordinatorGeometry(nodes, coordinator, local?.node_id ?? null, computedGeometry),
    [nodes, coordinator, local?.node_id, computedGeometry]);
  const geometry = geometrySelection.solution;
  const graphDiagnostics = useMemo(() => diagnoseGeometryGraph(geometryNodes), [geometryNodes]);
  const geometryState = geometry?.state ?? 'GEOMETRY_INSUFFICIENT';

  useEffect(() => { try { BodyFinderNative.updateGeometryState(geometryState); } catch {} }, [geometryState]);

  const validationTruth = useMemo(() => ({
    geometry,
    locally_computed_geometry: computedGeometry,
    authoritative_presence: presence,
    coordinator_node_id: coordinator,
    fused_range_observations: geometryNodes.flatMap(node => node.ranges ?? []),
    graph_diagnostics: graphDiagnostics,
    reciprocal_fusion: fused.diagnostics,
    measurement_health: {
      health: graphDiagnostics.measurement_health,
      physical_confidence: graphDiagnostics.physical_confidence,
      fresh_metric_edge_count: graphDiagnostics.fresh_metric_edge_count,
      holdover_metric_edge_count: graphDiagnostics.holdover_metric_edge_count,
      geometry_temporal_quality: graphDiagnostics.geometry_temporal_quality,
    },
  }), [geometry, computedGeometry, presence, coordinator, geometryNodes, graphDiagnostics, fused.diagnostics]);

  useEffect(() => {
    try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}
  }, [validationTruth]);

  useEffect(() => {
    const elected = Boolean(local?.node_id && coordinator === local.node_id);
    const publication = elected && computedGeometry ? {...computedGeometry, authoritative_presence: {...localPresenceDiagnostic, authoritative:true, source:'coordinator'}} : null;
    try { BodyFinderNative.updatePublishedGeometry(elected, publication ? JSON.stringify(publication) : null); } catch {}
  }, [local?.node_id, coordinator, computedGeometry, localPresenceDiagnostic]);

  useEffect(() => {
    if (!geometry) { visualFrame.current = null; setVisualPositions({}); return; }
    const sameFrame = visualFrame.current === geometry.frame_id;
    setVisualPositions(previous => {
      const next: Record<string, VisualPosition> = {};
      for (const position of geometry.positions) {
        const old = sameFrame ? previous[position.node_id] : undefined;
        const alpha = old ? 0.35 : 1;
        next[position.node_id] = { x_m: old ? old.x_m + alpha * (position.x_m - old.x_m) : position.x_m,
          y_m: old ? old.y_m + alpha * (position.y_m - old.y_m) : position.y_m };
      }
      return next;
    });
    visualFrame.current = geometry.frame_id;
  }, [geometry]);

  const arrayTarget = useMemo(() => estimateHuman(geometryNodes, geometry), [geometryNodes, geometry]);
  const localGeometry = useMemo(() => geometry?.positions.find(position => position.node_id === local?.node_id), [geometry, local?.node_id]);
  const target = useMemo(() => RELEASE.humanLocalizationValidated ? relativeTarget(arrayTarget, localGeometry) : null, [arrayTarget, localGeometry]);
  const evidenceCount = nodes.reduce((count, node) => count + (node.ranges?.length ?? 0), 0);
  const metricCount = graphDiagnostics.metric_sample_count;
  const proximityCount = graphDiagnostics.proximity_only_sample_count;
  const unresolved = Math.max(0, nodes.length - (geometry?.positions.length ?? 0));
  const visualLocal = local?.node_id ? visualPositions[local.node_id] : undefined;
  const blePeerCount = Array.isArray(diagnostics?.ble_diagnostics?.peers) ? diagnostics.ble_diagnostics.peers.filter((peer: any) => peer.binding_state !== 'UDP_ONLY').length : 0;
  const physicalConfidence = graphDiagnostics.physical_confidence;
  const holdoverEdgeCount = graphDiagnostics.holdover_metric_edge_count;
  const temporalQuality = graphDiagnostics.geometry_temporal_quality;

  async function calibrate() {
    setCalibrating(true); setScanning(false); setError(null);
    const samples: number[] = [];
    try {
      for (let i = 0; i < 32; i++) { const rssi = BodyFinderNative.getWifiRssi(); if (typeof rssi === 'number') samples.push(rssi); await sleep(250); }
      if (samples.length < 8) throw new Error(lang === 'es' ? 'No hay suficientes muestras RSSI Wi‑Fi reales.' : 'Not enough live Wi-Fi RSSI samples.');
      const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
      const standardDeviation = Math.max(1, Math.sqrt(samples.reduce((sum, value) => sum + (value - mean) ** 2, 0) / samples.length));
      setBaseline(mean); setSigma(standardDeviation);
    } catch (cause: any) { setError(String(cause?.message ?? cause)); } finally { setCalibrating(false); }
  }

  function refreshValidationState() {
    const fresh = JSON.parse(BodyFinderNative.getDiagnosticsJson());
    setDiagnostics(fresh);
    setValidationRun(fresh?.validation_run ?? null);
    return fresh;
  }

  function selectValidationRun(runId: string) {
    try {
      if (BodyFinderNative.selectValidationRun(runId)) refreshValidationState();
    } catch (cause: any) { setError(String(cause?.message ?? cause)); }
  }

  function toggleValidationRun() {
    if (validationActionLock.current) return;
    validationActionLock.current = true;
    try {
      if (validationRun?.active) {
        try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}
        BodyFinderNative.endValidationRun();
        setValidationNotice(lang === 'es' ? 'Corrida finalizada y congelada.' : 'Run completed and frozen.');
      } else {
        const retained = Array.isArray(diagnostics?.completed_validation_runs_summary) ? diagnostics.completed_validation_runs_summary.length : 0;
        if (retained > 0) setValidationNotice(lang === 'es' ? 'La corrida completada anterior se conservará en el historial.' : 'The previous completed run will be preserved in history.');
        const result = BodyFinderNative.startValidationRun();
        if (typeof result === 'string' && result.startsWith('VALIDATION_ENVIRONMENT_INVALID:')) {
          const reason = result.split(':').slice(1).join(':');
          setError(lang === 'es' ? `Ambiente de validación inválido: ${reason}. Desactiva Battery Saver, mantén pantalla encendida y Body Finder en primer plano.` : `Invalid validation environment: ${reason}. Turn Battery Saver off, keep the screen on and Body Finder in foreground.`);
          return;
        }
      }
      refreshValidationState();
    } catch (cause: any) { setError(String(cause?.message ?? cause)); }
    finally { setTimeout(() => { validationActionLock.current = false; }, 600); }
  }

  async function share() {
    let freshDiagnostics = diagnostics;
    let calibrationSnapshot: any = null;
    let autoFinalizedValidationRun = false;
    try {
      freshDiagnostics = JSON.parse(BodyFinderNative.getDiagnosticsJson());
      if (freshDiagnostics?.validation_run?.active) {
        try { BodyFinderNative.updateValidationTruthJson(JSON.stringify(validationTruth)); } catch {}
        BodyFinderNative.endValidationRun();
        autoFinalizedValidationRun = true;
        freshDiagnostics = JSON.parse(BodyFinderNative.getDiagnosticsJson());
        setDiagnostics(freshDiagnostics);
        setValidationRun(freshDiagnostics?.validation_run ?? null);
      }
    } catch {}
    try { calibrationSnapshot = JSON.parse(BodyFinderNative.getCalibrationSnapshotJson()); } catch {}
    const selectedRun = freshDiagnostics?.validation_run ?? null;
    const selectedRunId = typeof selectedRun?.run_id === 'string' ? selectedRun.run_id : 'no-run';
    const exportSequence = (exportSequenceByRun.current[selectedRunId] ?? 0) + 1;
    exportSequenceByRun.current[selectedRunId] = exportSequence;
    const completedRuns = Array.isArray(freshDiagnostics?.completed_validation_runs_summary) ? freshDiagnostics.completed_validation_runs_summary : [];
    const runType = selectedRun?.short_diagnostic_run === true ? 'SHORT' : 'LONG';
    const runEnded = typeof selectedRun?.ended_wall_ms === 'number' ? selectedRun.ended_wall_ms : 0;
    const laterShort = runType === 'LONG' && completedRuns.some((run: any) => run?.short_diagnostic_run === true && typeof run?.ended_wall_ms === 'number' && run.ended_wall_ms > runEnded);
    const snapshotStage = runType === 'SHORT' ? 'SHORT' : laterShort ? 'LONG_POST_SHORT' : exportSequence === 1 ? 'LONG_1' : 'LONG_2';
    const priorLong = completedRuns.filter((run: any) => run?.short_diagnostic_run === false && typeof run?.ended_wall_ms === 'number' && run.ended_wall_ms <= runEnded).sort((x: any, y: any) => (x.ended_wall_ms ?? 0) - (y.ended_wall_ms ?? 0)).at(-1);
    const sourceLongRunId = runType === 'SHORT' ? priorLong?.run_id ?? null : selectedRunId;
    const deviceAlias = String(caps?.model ?? local?.display_name ?? 'android-device').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const suggestedFilename = `${deviceAlias}-${selectedRunId.slice(0, 8)}-${snapshotStage.toLowerCase().replaceAll('_', '-')}.json`;
    const payload = {
      report_version: REPORT_VERSION,
      generated_at: new Date().toISOString(), app: 'Body Finder – RuView', build: BUILD, protocol_version: 2,
      json_self_contained: true, screenshots_required: false,
      export_metadata: {
        device_alias: deviceAlias, device_manufacturer: caps?.manufacturer ?? null, device_model: caps?.model ?? null,
        node_id: local?.node_id ?? null, run_id: selectedRunId, run_type: runType, snapshot_stage: snapshotStage,
        elapsed_ms: selectedRun?.elapsed_ms ?? null, snapshot_frozen: selectedRun?.snapshot_frozen ?? false,
        source_long_run_id: sourceLongRunId, export_sequence: exportSequence, generated_at: new Date().toISOString(),
        build: BUILD, protocol_version: 2, suggested_filename: suggestedFilename,
      },
      truth: 'LIVE_DEVICE_CAPABILITIES__VALIDATED_COARSE_BLE_METRIC_0P5_TO_5M__BOUNDED_HOLDOVER__ADAPTIVE_FILTERED_PRIMARY_WITH_FULL_COHORT_AND_PER_PEER_STARVATION_RECOVERY__RANGING_MANAGER_BLE_YIELD__RECIPROCAL_FUSION__AUTOGEOMETRY_EXPERIMENTAL_NOT_RESCUE_VALIDATED',
      evidence_contract: {
        schema: 'dev20.3-self-contained-json-evidence-v6', screenshots_required: false, json_self_contained: true,
        required_external_input: 'ground_truth_and_scenario_metadata_only_for_final_validator',
        diagnostic_source: 'this JSON export',
      },
      manual_geometry_override: false, human_scanning_enabled: HUMAN_SCANNING_ENABLED,
      human_presence_preview: presence,
      human_localization_validated: RELEASE.humanLocalizationValidated, rescue_use_validated: RELEASE.rescueUseValidated,
      export_auto_finalized_validation_run: autoFinalizedValidationRun,
      node_id: local?.node_id ?? null, capabilities: caps,
      ble_diagnostics: freshDiagnostics?.ble_diagnostics ?? null,
      fabric_diagnostics: freshDiagnostics?.fabric_diagnostics ?? null,
      lifecycle_diagnostics: freshDiagnostics?.lifecycle_diagnostics ?? null,
      validation_preflight: freshDiagnostics?.validation_preflight ?? null,
      diagnostic_contract: freshDiagnostics?.diagnostic_contract ?? null,
      selected_validation_run_id: freshDiagnostics?.selected_validation_run_id ?? null,
      validation_run: freshDiagnostics?.validation_run ?? null,
      completed_validation_runs_summary: freshDiagnostics?.completed_validation_runs_summary ?? [],
      calibration_snapshot: calibrationSnapshot,
      local, peers, coordinator_node_id: coordinator, geometry_source: geometrySelection.source, geometry,
      locally_computed_geometry: computedGeometry, graph_diagnostics: graphDiagnostics,
      reciprocal_fusion: fused.diagnostics,
      fused_range_observations: geometryNodes.flatMap(node => node.ranges ?? []),
      measurement_health: {
        health: graphDiagnostics.measurement_health,
        physical_confidence: physicalConfidence,
        metric_sample_count: metricCount,
        fresh_metric_edge_count: graphDiagnostics.fresh_metric_edge_count,
        holdover_metric_edge_count: graphDiagnostics.holdover_metric_edge_count,
        oldest_metric_edge_age_ms: graphDiagnostics.oldest_metric_edge_age_ms,
        geometry_temporal_quality: graphDiagnostics.geometry_temporal_quality,
        proximity_only_sample_count: proximityCount,
        saturated_sample_count: graphDiagnostics.saturated_sample_count,
        out_of_domain_sample_count: graphDiagnostics.out_of_domain_sample_count,
        invalid_rssi_sample_count: graphDiagnostics.invalid_rssi_sample_count,
        native_invalid_rssi_total_count: freshDiagnostics?.ble_diagnostics?.invalid_rssi_total_count ?? 0,
        reciprocal_disagreement_count: graphDiagnostics.reciprocal_disagreement_count,
      },
      range_observations: nodes.flatMap(node => node.ranges ?? []), estimate_array_frame: arrayTarget,
      estimate_relative_to_this_device: target,
      self_diagnostic: {
        acceptance_duration_eligible: Boolean(freshDiagnostics?.validation_run?.acceptance_duration_eligible),
        environment_valid: Boolean(freshDiagnostics?.validation_run?.environment_valid),
        snapshot_frozen: Boolean(freshDiagnostics?.validation_run?.snapshot_frozen),
        usable_metric_gate_pass: typeof freshDiagnostics?.validation_run?.usable_metric_range_uptime_percent === 'number' && freshDiagnostics.validation_run.usable_metric_range_uptime_percent >= 90,
        geometry_2d_gate_pass: typeof freshDiagnostics?.validation_run?.geometry_2d_uptime_percent === 'number' && freshDiagnostics.validation_run.geometry_2d_uptime_percent >= 90,
        peer_expire_gate_pass: freshDiagnostics?.validation_run?.peer_expire_delta === 0,
        recovery_budget_gate_pass: typeof freshDiagnostics?.validation_run?.recovery_attempt_delta === 'number' && freshDiagnostics.validation_run.recovery_attempt_delta <= 3,
      },
      instructions: 'Return exported JSON files only; screenshots are unnecessary. Acceptance requires >=330 s, valid EMPTY_CAL, 3 nodes/6 directional links/3 baselines, peer authoritative consistency and offline replay parity. Human localization and rescue use remain unvalidated.',
    };
    const serializedPayload = JSON.stringify(payload, null, 2);
    if (Platform.OS === 'android') {
      const shared = BodyFinderNative.shareJsonFile(serializedPayload, suggestedFilename);
      if (!shared) throw new Error(lang === 'es' ? 'No se pudo preparar el archivo JSON para compartir.' : 'Could not prepare the JSON file for sharing.');
    } else {
      await Share.share({ message: serializedPayload, title: suggestedFilename });
    }
  }

  const scale = 18;
  const geometryLabel = metricCount === 0 && evidenceCount > 0 ? 'GEOMETRY UNTRUSTED / NO METRIC RANGE' : geometryState.replaceAll('_', ' ');
  return (
    <SafeAreaView style={s.safe}>
      <ExpoStatusBar style="light" translucent={false} backgroundColor="#071016" />
      <View style={s.header}><View style={s.headerText}><Text style={s.title}>{tx.title}</Text><Text style={s.warn}>{tx.experimental}</Text></View>
        <Pressable onPress={() => setLang(lang === 'en' ? 'es' : 'en')}><Text style={s.link}>{lang.toUpperCase()}</Text></Pressable></View>
      <View style={s.tabs}>
        <Pressable style={[s.tab, mode === 'radar' && s.tabOn]} onPress={() => setMode('radar')}><Text style={s.tabText}>{tx.radar}</Text></Pressable>
        <Pressable style={[s.tab, mode === 'expert' && s.tabOn]} onPress={() => setMode('expert')}><Text style={s.tabText}>{tx.expert}</Text></Pressable>
      </View>
      {mode === 'radar' ? (
        <ScrollView contentContainerStyle={s.body}>
          <View style={s.statusRow}>
            <Text style={s.pill}>{nodes.length} {tx.peers}</Text><Text style={s.pill}>{metricCount} METRIC</Text>
            <Text style={s.pill}>{holdoverEdgeCount} HOLD</Text><Text style={s.pill}>{proximityCount} PROX</Text><Text style={s.pill}>{blePeerCount} BLE PEERS</Text><Text style={s.pill}>COORD {coordinator?.slice(-8) ?? '—'}</Text>
          </View>
          <Text style={s.network}>{tx.network}</Text>
          <View style={s.card}>
            <Text style={s.h2}>{tx.geometry}</Text><Text style={[s.geometryState, metricCount === 0 && evidenceCount > 0 && s.geometryWarn]}>{geometryLabel}</Text>
            <Text style={s.text}>{geometry?.positions.length ?? 0}/{nodes.length} {tx.positioned} · {geometry?.dimension ?? 'UNKNOWN'} AUTO</Text>
            <Text style={s.text}>{tx.residual}: {geometry?.residual_rms_m != null ? `${geometry.residual_rms_m.toFixed(2)} m` : '—'} · {tx.condition}: {geometry?.condition_score != null ? `${(100 * geometry.condition_score).toFixed(0)}%` : '—'}</Text>
            <Text style={s.text}>measurement health: {graphDiagnostics.measurement_health} · physical confidence: {physicalConfidence}</Text>
            <Text style={s.text}>temporal quality: {temporalQuality} · fresh edges: {graphDiagnostics.fresh_metric_edge_count} · holdover edges: {holdoverEdgeCount}</Text>
            <Text style={s.text}>oldest metric age: {graphDiagnostics.oldest_metric_edge_age_ms != null ? `${graphDiagnostics.oldest_metric_edge_age_ms.toFixed(0)} ms` : '—'} · proximity: {proximityCount} · out-of-domain: {graphDiagnostics.out_of_domain_sample_count}</Text>
            <Text style={s.text}>revision: {geometry?.revision ?? '—'} · source: {geometrySelection.source}</Text>
            <Text style={s.muted}>{metricCount === 0 && evidenceCount > 0 ? 'BLE peers are visible, but no validated in-domain fresh or bounded-holdover metric range is currently usable.' : geometry?.reason ?? tx.estimating}</Text>
            {unresolved > 0 && <Text style={s.muted}>{unresolved} {tx.unresolved}</Text>}
          </View>
          <Text style={s.relative}>{tx.relative}</Text>
          <View style={s.radar}>
            {[90, 180, 270].map(diameter => <View key={diameter} style={[s.ring, { width: diameter, height: diameter, borderRadius: diameter / 2, left: 150 - diameter / 2, top: 150 - diameter / 2 }]} />)}
            <View style={s.operator} />
            {visualLocal && geometry?.positions.filter(position => position.node_id !== local?.node_id && visualPositions[position.node_id]).map((position, index) => {
              const relative = relativeVisualPosition(visualPositions[position.node_id], visualLocal);
              const diameter = Math.min(90, Math.max(10, position.error_radius_95_m * scale * 2));
              return <React.Fragment key={position.node_id}><View style={[s.sensorUncertainty, { width: diameter, height: diameter, borderRadius: diameter / 2, left: 150 + relative.x_m * scale - diameter / 2, top: 150 - relative.y_m * scale - diameter / 2 }]} />
                <View style={[s.sensor, { left: 144 + relative.x_m * scale, top: 144 - relative.y_m * scale }]}><Text style={s.dotLabel}>{index + 1}</Text></View></React.Fragment>;
            })}
            {target && scanning && <><View style={[s.targetRing, { width: Math.min(260, target.error_radius_95_m * 36), height: Math.min(260, target.error_radius_95_m * 36), borderRadius: 130, left: 150 - Math.min(260, target.error_radius_95_m * 36) / 2 + target.x_m * scale, top: 150 - Math.min(260, target.error_radius_95_m * 36) / 2 - target.y_m * scale }]} /><View style={[s.target, { left: 144 + target.x_m * scale, top: 144 - target.y_m * scale }]} /></>}
          </View>
          {target && scanning ? <View style={s.card}><Text style={s.h2}>{target.state.replace('_', ' ')}</Text><Text style={s.big}>{target.range_m.toFixed(1)} m · {target.bearing_deg.toFixed(0)}°</Text>
            <Text style={s.text}>x {target.x_m.toFixed(2)} m · y {target.y_m.toFixed(2)} m</Text><Text style={s.text}>{tx.confidence}: {(target.human_confidence * 100).toFixed(0)}%</Text>
            <Text style={s.text}>{tx.uncertainty}: {target.uncertainty_percent.toFixed(0)}% · ±{target.error_radius_95_m.toFixed(1)} m (95%)</Text><Text style={s.muted}>{tx.evidence}</Text></View>
            : <View style={s.card}><Text style={s.h2}>{scanning ? presence.prediction.replaceAll('_', ' ') : 'PRESENCE SCAN IDLE'}</Text><Text style={s.text}>{scanning ? `${tx.confidence}: ${(presence.human_confidence * 100).toFixed(0)}% · ${presence.evidence_quality}` : tx.noTarget}</Text><Text style={s.muted}>{scanning ? presence.reason : tx.evidence}</Text></View>}
          <View style={s.card}><Text style={s.h2}>Validation run</Text><Text style={s.text}>run: {validationRun?.run_id ?? '—'} · active: {String(Boolean(validationRun?.active))}</Text>
            <Text style={s.text}>elapsed: {validationRun?.elapsed_ms ?? 0} ms · acceptance ≥300s: {String(Boolean(validationRun?.acceptance_duration_eligible))} · frozen: {String(Boolean(validationRun?.snapshot_frozen))} · schema: {validationRun?.snapshot_schema_version ?? RELEASE.snapshotSchemaVersion}</Text>
            <Text style={s.text}>ended: {validationRun?.ended_wall_ms ?? '—'} · retained: {diagnostics?.completed_validation_runs_summary?.length ?? 0}/5 · selected: {diagnostics?.selected_validation_run_id?.slice?.(-8) ?? '—'}</Text>
            <Text style={s.text}>peer expiry Δ: {validationRun?.peer_expire_delta ?? 0} · rebind Δ: {validationRun?.address_rebind_delta ?? 0}</Text>
            <Text style={s.text}>peer: {formatPct(validationRun?.all_peer_uptime_percent)} · fresh metric: {formatPct(validationRun?.fresh_metric_range_uptime_percent)} · usable metric: {formatPct(validationRun?.usable_metric_range_uptime_percent)}</Text>
            <Text style={s.text}>holdover share: {formatPct(validationRun?.holdover_metric_uptime_percent)} · 2D: {formatPct(validationRun?.geometry_2d_uptime_percent)}</Text><Text style={s.text}>recovery attempts Δ: {validationRun?.recovery_attempt_delta ?? 0} · suppressed Δ: {validationRun?.restart_suppressed_delta ?? 0} · cohort stalls Δ: {validationRun?.cohort_stall_delta ?? 0}</Text>
            {validationNotice && <Text style={s.muted}>{validationNotice}</Text>}
            {Array.isArray(diagnostics?.completed_validation_runs_summary) && diagnostics.completed_validation_runs_summary.map((run: any) => <Pressable key={run.run_id} style={s.btnAlt} onPress={() => selectValidationRun(run.run_id)}><Text style={s.btnText}>{run.run_id.slice(0, 8)} · {Math.round((run.elapsed_ms ?? 0) / 1000)}s · frozen {String(run.snapshot_frozen)}</Text></Pressable>)}
          </View>
          <Pressable style={s.btnTest} onPress={toggleValidationRun}><Text style={s.btnText}>{validationRun?.active ? tx.endRun : tx.startRun}</Text></Pressable>
          <Text style={s.muted}>{tx.empty}</Text>
          <Pressable disabled={calibrating} style={s.btn} onPress={calibrate}><Text style={s.btnText}>{calibrating ? 'CALIBRATING…' : tx.calibrate}</Text></Pressable>
          <Pressable disabled={!HUMAN_SCANNING_ENABLED || baseline == null || physicalConfidence === 'NONE'} style={[s.btn, (!HUMAN_SCANNING_ENABLED || baseline == null || physicalConfidence === 'NONE') && s.disabled]} onPress={() => setScanning(value => !value)}><Text style={s.btnText}>{scanning ? tx.stop : tx.scanning}</Text></Pressable>
          <Pressable style={s.btnAlt} onPress={share}><Text style={s.btnText}>{tx.share}</Text></Pressable>{error && <Text style={s.err}>{error}</Text>}
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={s.body}>
          <View style={s.card}><Text style={s.h2}>Truth / source classification</Text><Text style={s.text}>Build: {BUILD} · protocol 2</Text>
            <Text style={s.text}>Node geometry: AUTO ONLY — manual override disabled</Text><Text style={s.text}>Geometry authority: {geometrySelection.source}</Text>
            <Text style={s.text}>BLE RSSI: validated COARSE profile android-ble-lab-v1 only inside 0.5–5.0 m. Profile parameters are frozen from dev-6.</Text>
            <Text style={s.text}>Continuity: fresh metric estimates may enter a bounded 10 s HOLDOVER when samples briefly disappear; sigma increases with age and hard expiry removes the edge.</Text>
            <Text style={s.text}>Acquisition: experimental.16 uses manufacturer-filtered LOW_LATENCY scanning as FILTERED_PRIMARY. CALLBACK_TYPE_ALL_MATCHES is only the Android callback setting inside the filtered scan; the no-filter path is bounded UNFILTERED_RECOVERY only.</Text>
            <Text style={s.text}>API36+: repeated RangingManager close/no-result churn enters a bounded BLE-acquisition yield; only a real platform distance resets system-ranging failures.</Text>
            <Text style={s.text}>RSSI 127 and other invalid values are filtered before the valid queue and are counted separately for diagnostics.</Text>
            <Text style={s.text}>Reciprocal A↔B BLE observations are inverse-variance fused before the solver; REJECT never enters geometry.</Text>
            <Text style={s.text}>Human scanning: BLOCKED until the experimental.16 validation-integrity gate is reviewed.</Text>
            <Text style={s.text}>Graph condition is not physical accuracy. CSI remains unsupported unless a verified adapter is loaded.</Text></View>
          <Pressable style={s.btnTest} onPress={toggleValidationRun}><Text style={s.btnText}>{validationRun?.active ? tx.endRun : tx.startRun}</Text></Pressable>
          {[
            ['Measurement health', { measurement_health: graphDiagnostics.measurement_health, physical_confidence: physicalConfidence, geometry_temporal_quality: graphDiagnostics.geometry_temporal_quality, fresh_metric_edge_count: graphDiagnostics.fresh_metric_edge_count, holdover_metric_edge_count: graphDiagnostics.holdover_metric_edge_count, oldest_metric_edge_age_ms: graphDiagnostics.oldest_metric_edge_age_ms, metric_edge_pairs: graphDiagnostics.metric_edge_pairs, proximity_only_sample_count: proximityCount, out_of_domain_sample_count: graphDiagnostics.out_of_domain_sample_count, native_invalid_rssi_total_count: diagnostics?.ble_diagnostics?.invalid_rssi_total_count ?? 0, reciprocal_disagreement_count: graphDiagnostics.reciprocal_disagreement_count }],
            ['Reciprocal fusion', fused.diagnostics],
            ['Validation preflight', diagnostics?.validation_preflight ?? null], ['Validation run', diagnostics?.validation_run ?? null], ['Lifecycle / power diagnostics', diagnostics?.lifecycle_diagnostics ?? null],
            ['BLE / ranging diagnostics', diagnostics?.ble_diagnostics ?? null], ['Fabric diagnostics', diagnostics?.fabric_diagnostics ?? null],
            ['Geometry solution', geometry], ['Locally computed geometry', computedGeometry], ['Graph diagnostics / temporal quality', graphDiagnostics],
            ['Raw range / proximity observations', nodes.flatMap(node => node.ranges ?? [])], ['Fused geometry observations', geometryNodes.flatMap(node => node.ranges ?? [])], ['Capabilities', caps], ['Local node', local], ['Peers', peers],
            ['Array-frame estimate', arrayTarget], ['Relative estimate', target],
          ].map(([name, value]) => <View style={s.card} key={String(name)}><Text style={s.h2}>{String(name)}</Text><Text selectable style={s.code}>{JSON.stringify(value, null, 2)}</Text></View>)}
          <Pressable style={s.btnAlt} onPress={share}><Text style={s.btnText}>{tx.share}</Text></Pressable>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function formatPct(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}%` : '—'; }

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#071016', paddingTop: Platform.OS === 'android' ? Math.max(0, NativeStatusBar.currentHeight ?? 0) : 0 },
  header: { padding: 16, paddingTop: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }, headerText: { flex: 1, paddingRight: 8 },
  title: { color: '#e8f7ff', fontSize: 22, fontWeight: '800' }, warn: { color: '#ffb35c', fontSize: 10, fontWeight: '700', marginTop: 3 },
  link: { color: '#66d7ff', fontWeight: '800', padding: 8 }, tabs: { flexDirection: 'row', paddingHorizontal: 12, gap: 8 },
  tab: { flex: 1, padding: 10, borderRadius: 10, backgroundColor: '#0d1b24', alignItems: 'center' }, tabOn: { backgroundColor: '#15384a' }, tabText: { color: '#e6f6ff', fontWeight: '700' },
  body: { padding: 14, paddingBottom: 48, gap: 10 }, statusRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  pill: { color: '#b7eaff', backgroundColor: '#102935', paddingHorizontal: 9, paddingVertical: 5, borderRadius: 99, fontSize: 11, fontWeight: '700' },
  network: { color: '#ffcb76', fontSize: 10, fontWeight: '700' }, relative: { color: '#8edfff', fontSize: 11, fontWeight: '800', textAlign: 'center', marginTop: 2 },
  radar: { width: 300, height: 300, alignSelf: 'center', position: 'relative', overflow: 'hidden', borderRadius: 150, backgroundColor: '#081a22' },
  ring: { position: 'absolute', borderWidth: 1, borderColor: '#1d4556' }, operator: { position: 'absolute', left: 144, top: 144, width: 12, height: 12, borderRadius: 6, backgroundColor: '#fff' },
  sensorUncertainty: { position: 'absolute', borderWidth: 1, borderColor: '#2f7390' }, sensor: { position: 'absolute', width: 12, height: 12, borderRadius: 6, backgroundColor: '#58c8ff', alignItems: 'center', justifyContent: 'center' },
  dotLabel: { fontSize: 8, fontWeight: '900', color: '#001018' }, target: { position: 'absolute', width: 12, height: 12, borderRadius: 6, backgroundColor: '#ff9d55' }, targetRing: { position: 'absolute', borderWidth: 1, borderColor: '#ff9d55' },
  card: { backgroundColor: '#0d1b24', borderRadius: 14, padding: 13, gap: 4 }, h2: { color: '#bfeeff', fontSize: 13, fontWeight: '800' },
  geometryState: { color: '#72e5a1', fontSize: 18, fontWeight: '900' }, geometryWarn: { color: '#ffcb76' }, big: { color: '#fff', fontSize: 23, fontWeight: '800' },
  text: { color: '#dfedf3', fontSize: 13 }, muted: { color: '#8198a4', fontSize: 11 }, code: { color: '#b9d2dc', fontSize: 10, fontFamily: Platform.select({ android: 'monospace', ios: 'Menlo' }) },
  btn: { backgroundColor: '#16688b', padding: 13, borderRadius: 12, alignItems: 'center' }, btnTest: { backgroundColor: '#285b6d', padding: 13, borderRadius: 12, alignItems: 'center' },
  btnAlt: { backgroundColor: '#263845', padding: 13, borderRadius: 12, alignItems: 'center' }, disabled: { opacity: 0.4 }, btnText: { color: '#fff', fontWeight: '800' }, err: { color: '#ff8a8a', fontSize: 12 },
});
