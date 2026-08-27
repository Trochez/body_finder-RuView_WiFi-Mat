#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KT = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
VERSION = ROOT / "apps/mobile/src/version.ts"
APPJSON = ROOT / "apps/mobile/app.json"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def replace_all_checked(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} matches, found {count}")
    return text.replace(old, new)


s = KT.read_text()

s = replace_once(
    s,
    'private const val PEER_EXPIRY_MS = 5_000L',
    'private const val PEER_STALE_MS = 5_000L\nprivate const val PEER_EXPIRY_MS = 10_000L',
    'two-stage peer timeout constants',
)

s = replace_once(
    s,
    '  val peerLastSeenWallMs = ConcurrentHashMap<String, Long>()\n',
    '  val peerLastSeenWallMs = ConcurrentHashMap<String, Long>()\n'
    '  val peerLastSeenMonotonicNs = ConcurrentHashMap<String, Long>()\n'
    '  val peerStaleSinceWallMs = ConcurrentHashMap<String, Long>()\n',
    'fabric peer continuity maps',
)

s = replace_once(
    s,
    '    peerLastSeenWallMs.clear()\n',
    '    peerLastSeenWallMs.clear()\n'
    '    peerLastSeenMonotonicNs.clear()\n'
    '    peerStaleSinceWallMs.clear()\n',
    'fabric reset maps',
)

s = replace_once(
    s,
    '  @Volatile private var allExpectedPeerMetricUptimeMs: Long = 0\n',
    '  @Volatile private var allExpectedPeerMetricUptimeMs: Long = 0\n'
    '  @Volatile private var expectedPeerCountAtStart: Int = 0\n'
    '  @Volatile private var expectedPeerIdsAtStart: List<String> = emptyList()\n',
    'validation frozen cohort state',
)

s = replace_once(
    s,
    '    preflightAtStartJson = try { JSONObject(preflightJson).toString() } catch (_: Throwable) { "{}" }\n',
    '    val frozenPreflight = try { JSONObject(preflightJson) } catch (_: Throwable) { JSONObject() }\n'
    '    preflightAtStartJson = frozenPreflight.toString()\n'
    '    val frozenPeerIds = frozenPreflight.optJSONArray("expected_ble_peer_ids") ?: JSONArray()\n'
    '    expectedPeerIdsAtStart = (0 until frozenPeerIds.length()).mapNotNull { frozenPeerIds.optString(it).takeIf(String::isNotBlank) }.distinct().sorted()\n'
    '    expectedPeerCountAtStart = max(frozenPreflight.optInt("expected_ble_peer_count", expectedPeerIdsAtStart.size), expectedPeerIdsAtStart.size)\n'
    '    FabricEventTimeline.start(id, now, expectedPeerIdsAtStart)\n',
    'freeze validation cohort',
)

s = replace_once(
    s,
    '  @Synchronized\n  fun observe(now: Long, activePeerCount: Int, evidenceReadyPeerCount: Int, freshMetricReadyPeerCount: Int, usableMetricReadyPeerCount: Int) {\n',
    '  @Synchronized\n'
    '  fun frozenExpectedPeerCount(): Int = expectedPeerCountAtStart\n\n'
    '  @Synchronized\n'
    '  fun frozenExpectedPeerIds(): List<String> = expectedPeerIdsAtStart.toList()\n\n'
    '  @Synchronized\n'
    '  fun observe(now: Long, activePeerCount: Int, evidenceReadyPeerCount: Int, freshMetricReadyPeerCount: Int, usableMetricReadyPeerCount: Int) {\n',
    'validation cohort getters',
)

s = replace_once(
    s,
    '    if (activePeerCount >= 2) peerFullUptimeMs += dt\n'
    '    if (evidenceReadyPeerCount >= 2) rangeEvidenceUptimeMs += dt\n'
    '    if (freshMetricReadyPeerCount >= 2) freshMetricRangeUptimeMs += dt\n'
    '    if (usableMetricReadyPeerCount >= 2) usableMetricRangeUptimeMs += dt\n'
    '    if (usableMetricReadyPeerCount >= 1) singleRemotePeerMetricUptimeMs += dt\n'
    '    if (activePeerCount > 0 && usableMetricReadyPeerCount >= activePeerCount) allExpectedPeerMetricUptimeMs += dt\n'
    '    if (usableMetricReadyPeerCount >= 2 && freshMetricReadyPeerCount < 2) holdoverMetricUptimeMs += dt\n',
    '    val expected = expectedPeerCountAtStart.coerceAtLeast(2)\n'
    '    if (activePeerCount >= expected) peerFullUptimeMs += dt\n'
    '    if (evidenceReadyPeerCount >= expected) rangeEvidenceUptimeMs += dt\n'
    '    if (freshMetricReadyPeerCount >= expected) freshMetricRangeUptimeMs += dt\n'
    '    if (usableMetricReadyPeerCount >= expected) usableMetricRangeUptimeMs += dt\n'
    '    if (usableMetricReadyPeerCount >= 1) singleRemotePeerMetricUptimeMs += dt\n'
    '    if (usableMetricReadyPeerCount >= expected) allExpectedPeerMetricUptimeMs += dt\n'
    '    if (usableMetricReadyPeerCount >= expected && freshMetricReadyPeerCount < expected) holdoverMetricUptimeMs += dt\n',
    'validation uptime denominator',
)

# Both live and frozen snapshots expose the immutable cohort. There are exactly two schema-version writes.
s = replace_all_checked(
    s,
    '      .put("snapshot_schema_version", 4)\n',
    '      .put("snapshot_schema_version", 4)\n'
    '      .put("expected_peer_count_at_start", expectedPeerCountAtStart)\n'
    '      .put("expected_peer_ids_at_start", JSONArray(expectedPeerIdsAtStart))\n',
    2,
    'snapshot frozen cohort fields',
)

s = replace_once(
    s,
    '      .put("preflight_at_start", try { JSONObject(preflightAtStartJson) } catch (_: Throwable) { JSONObject() })\n',
    '      .put("preflight_at_start", try { JSONObject(preflightAtStartJson) } catch (_: Throwable) { JSONObject() })\n'
    '      .put("fabric_event_timeline", FabricEventTimeline.snapshot(now))\n'
    '      .put("expected_peer_loss_intervals", FabricEventTimeline.lossIntervals(now))\n',
    'frozen fabric evidence',
)

s = replace_once(
    s,
    '    if (expectedKnownPeerCount() < 1) issues += "EXPECTED_BLE_PEERS_LT_1"\n',
    '    val expectedNow = expectedKnownPeerCount()\n'
    '    val requiredExpected = if (ValidationRuntime.runId != null && ValidationRuntime.endedWallMs == null) ValidationRuntime.frozenExpectedPeerCount().coerceAtLeast(2) else 2\n'
    '    if (expectedNow < requiredExpected) issues += "EXPECTED_BLE_PEER_COHORT_LOSS"\n',
    'strict expected peer cohort environment gate',
)

s = replace_once(
    s,
    '      .put("expected_ble_peer_count", expectedKnownPeerCount())\n'
    '      .put("expected_ble_peers", expectedKnownPeerCount())\n'
    '      .put("expected_ble_peers_ready", expectedKnownPeerCount() >= 1)\n',
    '      .put("expected_ble_peer_count", expectedKnownPeerCount())\n'
    '      .put("expected_ble_peers", expectedKnownPeerCount())\n'
    '      .put("expected_ble_peer_ids", JSONArray(FabricRuntime.peers.keys.toList().sorted()))\n'
    '      .put("expected_ble_peers_ready", expectedKnownPeerCount() >= 2)\n',
    'preflight cohort IDs and 2-peer readiness',
)

old_fabric_state = '        .put("state", if (FabricRuntime.peers.containsKey(nodeId)) "ACTIVE" else "EXPIRED"))\n'
new_fabric_state = '        .put("state", when {\n          !FabricRuntime.peers.containsKey(nodeId) -> "EXPIRED"\n          FabricRuntime.peerStaleSinceWallMs.containsKey(nodeId) -> "STALE"\n          else -> "ACTIVE"\n        }))\n'
s = replace_once(s, old_fabric_state, new_fabric_state, 'fabric diagnostics state')

old_expire = '''  private fun expirePeers(now: Long) {
    val expired = FabricRuntime.peers.entries
      .filter { now - it.value.second > PEER_EXPIRY_MS }
      .map { it.key }
    for (nodeId in expired) {
      if (FabricRuntime.peers.remove(nodeId) != null) {
        FabricRuntime.peerExpireCount.incrementAndGet()
        FabricRuntime.lastValidRangeByPeer.remove(nodeId)
      }
    }
  }
'''
new_expire = '''  private fun fabricTransitionDetails(ctx: Context, now: Long, nodeId: String, payload: String?, lastRxWallMs: Long?, stateBefore: String, stateAfter: String, reason: String): JSONObject {
    val peer = try { payload?.let(::JSONObject) } catch (_: Throwable) { null }
    val identity = peer?.optString("ble_identity")?.takeIf { it.isNotBlank() && it != "null" }
    val bleLast = identity?.let { FabricRuntime.lastValidRssiWallMsByIdentity[it] }
    val ranging = if (Build.VERSION.SDK_INT >= 36) SystemRangingApi36.diagnostics(now) else JSONObject().put("state", "UNSUPPORTED")
    return JSONObject()
      .put("wall_ms", now)
      .put("peer_id", nodeId)
      .put("reason", reason)
      .put("last_rx_wall_ms", lastRxWallMs ?: JSONObject.NULL)
      .put("last_rx_monotonic_ns", FabricRuntime.peerLastSeenMonotonicNs[nodeId] ?: JSONObject.NULL)
      .put("rx_gap_ms_at_transition", lastRxWallMs?.let { (now - it).coerceAtLeast(0L) } ?: JSONObject.NULL)
      .put("rx_packets_at_transition", FabricRuntime.peerPacketCounts[nodeId]?.get() ?: 0L)
      .put("peer_state_before", stateBefore)
      .put("peer_state_after", stateAfter)
      .put("expected_peer_count_at_start", ValidationRuntime.frozenExpectedPeerCount())
      .put("expected_peer_ids_at_start", JSONArray(ValidationRuntime.frozenExpectedPeerIds()))
      .put("active_peer_count_at_transition", FabricRuntime.peers.size)
      .put("scan_generation", FabricRuntime.scanGeneration.get())
      .put("ranging_manager_state", ranging.optString("state"))
      .put("ranging_yield_active", ranging.optBoolean("ble_yield_active"))
      .put("system_ranging", ranging)
      .put("ble_identity", identity ?: JSONObject.NULL)
      .put("ble_last_sample_age_ms", bleLast?.let { (now - it).coerceAtLeast(0L) } ?: JSONObject.NULL)
      .put("socket_state", FabricRuntime.socketState)
      .put("multicast_join_state", FabricRuntime.multicastJoinState)
      .put("lifecycle", lifecycleDiagnostics(ctx))
  }

  private fun expirePeers(ctx: Context, now: Long) {
    FabricRuntime.peers.entries.forEach { entry ->
      val nodeId = entry.key
      val gap = now - entry.value.second
      if (gap > PEER_STALE_MS && gap <= PEER_EXPIRY_MS && FabricRuntime.peerStaleSinceWallMs.putIfAbsent(nodeId, now) == null) {
        FabricEventTimeline.record(
          "PEER_BECAME_STALE",
          fabricTransitionDetails(ctx, now, nodeId, entry.value.first, entry.value.second, "ACTIVE", "STALE", "UDP_RX_GAP_EXCEEDED_STALE_THRESHOLD")
        )
      }
    }
    val expired = FabricRuntime.peers.entries
      .filter { now - it.value.second > PEER_EXPIRY_MS }
      .map { it.key }
    for (nodeId in expired) {
      val pair = FabricRuntime.peers[nodeId]
      val lastSeen = pair?.second ?: FabricRuntime.peerLastSeenWallMs[nodeId]
      if (pair != null) {
        FabricEventTimeline.record(
          "PEER_EXPIRED",
          fabricTransitionDetails(ctx, now, nodeId, pair.first, lastSeen, if (FabricRuntime.peerStaleSinceWallMs.containsKey(nodeId)) "STALE" else "ACTIVE", "EXPIRED", "UDP_RX_GAP_EXCEEDED_HARD_EXPIRY")
        )
      }
      if (FabricRuntime.peers.remove(nodeId) != null) {
        FabricRuntime.peerExpireCount.incrementAndGet()
        FabricRuntime.peerStaleSinceWallMs.remove(nodeId)
        FabricRuntime.lastValidRangeByPeer.remove(nodeId)
      }
    }
  }
'''
s = replace_once(s, old_expire, new_expire, 'two-stage expiry and causal telemetry')

old_rx = '''              val seen = System.currentTimeMillis()
              FabricRuntime.peers[remoteId] = text to seen
              FabricRuntime.peerLastSeenWallMs[remoteId] = seen
              FabricRuntime.peerPacketCounts.computeIfAbsent(remoteId) { AtomicLong(0) }.incrementAndGet()
'''
new_rx = '''              val seen = System.currentTimeMillis()
              val previousPair = FabricRuntime.peers[remoteId]
              val previousLastSeen = FabricRuntime.peerLastSeenWallMs[remoteId]
              val wasKnown = FabricRuntime.peerPacketCounts.containsKey(remoteId)
              val wasActive = previousPair != null
              val wasStale = FabricRuntime.peerStaleSinceWallMs.containsKey(remoteId)
              FabricRuntime.peers[remoteId] = text to seen
              FabricRuntime.peerLastSeenWallMs[remoteId] = seen
              FabricRuntime.peerLastSeenMonotonicNs[remoteId] = SystemClock.elapsedRealtimeNanos()
              FabricRuntime.peerPacketCounts.computeIfAbsent(remoteId) { AtomicLong(0) }.incrementAndGet()
              if (wasKnown && (!wasActive || wasStale)) {
                FabricEventTimeline.record(
                  "PEER_REACTIVATED",
                  fabricTransitionDetails(ctx, seen, remoteId, text, previousLastSeen, if (!wasActive) "EXPIRED" else "STALE", "ACTIVE", "UDP_RX_RESUMED")
                )
              }
              FabricRuntime.peerStaleSinceWallMs.remove(remoteId)
'''
s = replace_once(s, old_rx, new_rx, 'peer reactivation telemetry')

# The network loop owns Context; only this call site exists in the module.
s = replace_once(s, '          expirePeers(now)\n', '          expirePeers(ctx, now)\n', 'expirePeers context call')

KT.write_text(s)

v = VERSION.read_text()
v = v.replace("build: '0.2.0-experimental.18'", "build: '0.2.0-experimental.19'")
v = v.replace('reportVersion: 19', 'reportVersion: 20')
v = v.replace('versionCode: 18', 'versionCode: 19')
v = v.replace("releaseIteration: 'experimental.18'", "releaseIteration: 'experimental.19'")
if '0.2.0-experimental.19' not in v or 'versionCode: 19' not in v:
    raise SystemExit('version.ts patch failed')
VERSION.write_text(v)

a = APPJSON.read_text()
a = a.replace('"versionCode": 18', '"versionCode": 19')
a = a.replace('"releaseIteration": "experimental.18"', '"releaseIteration": "experimental.19"')
if '"versionCode": 19' not in a or 'experimental.19' not in a:
    raise SystemExit('app.json patch failed')
APPJSON.write_text(a)

print('dev19 peer continuity patch applied successfully')
