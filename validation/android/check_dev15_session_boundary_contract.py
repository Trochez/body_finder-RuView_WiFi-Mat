#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt"
POLICY = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BleAcquisitionPolicy.kt"
ENV = ROOT / "apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/EnvironmentStrategyValidator.kt"
VALIDATOR = ROOT / "validation/analysis/dev15_validation.py"

native = NATIVE.read_text()
policy = POLICY.read_text()
env = ENV.read_text()
validator = VALIDATOR.read_text()

required = {
    "session boundary method": "fun prepareValidationRunBoundary" in policy,
    "budget preserved": "PRESERVE_RECOVERY_BUDGET_AND_COOLDOWN" in policy,
    "active recovery not aborted": "BleAcquisitionStrategy.UNFILTERED_RECOVERY,\n      BleAcquisitionStrategy.FILTERED_RECOVERY_PROBE -> false" in policy,
    "nested first valid increment": "firstCallbackAfterRecoveryCount.incrementAndGet()" in policy,
    "recordScan nested counter hook": "acquisitionStats.noteFirstValidRecovery(recoveryGeneration, now)" in native,
    "completed-run boundary hook": "previousRunCompleted && physicalValidationIssues(ctx).isEmpty()" in native,
    "preflight boundary evidence": '.put("recovery_budget_preserved_across_boundary", true)' in native,
    "global stall uses current strategy": 'restartScannerWithStrategy(now, current, "GLOBAL_SCANNER_STALLED")' in native,
    "global stall recovery deadline": "RECOVERY_WINDOW_EXPIRED_GLOBAL_STALL" in native,
    "global stall probe deadline": "PROBE_EXIT_TARGET_GLOBAL_STALL" in native,
    "failed safe authorized": "AUTHORIZED_FAILED_SAFE_RECOVERY_BUDGET_GUARD" in env,
    "cooldown authorized": "AUTHORIZED_FILTERED_COOLDOWN" in env,
    "validator rejects failed safe end": "FAILED_SAFE_AT_END" in validator,
    "validator checks nested counter": "acquisition.run_first_callback_after_recovery_count" in validator,
}

# Safety invariant: the boundary method must not clear the rolling attempt deque,
# reset lifetime attempt totals, or change any frozen timing constants.
start = policy.find("fun prepareValidationRunBoundary")
end = policy.find("private fun isFiltered", start)
boundary = policy[start:end] if start >= 0 and end > start else ""
for forbidden in ("recoveryAttemptWallMs.clear()", "recoveryAttemptCountTotal = 0", "lastRecoveryAttemptWallMs = 0"):
    required[f"boundary does not weaken budget: {forbidden}"] = forbidden not in boundary

frozen = {
    "RECOVERY_UNFILTERED_WINDOW_MS = 10_000L",
    "FILTERED_PROBE_WINDOW_MS = 15_000L",
    "FILTERED_PROBE_EXIT_TARGET_MS = 14_500L",
    "MIN_RESTART_COOLDOWN_MS = 30_000L",
    "MAX_RECOVERY_ATTEMPTS_PER_5MIN = 3",
    "RECOVERY_ATTEMPT_WINDOW_MS = 300_000L",
}
for token in frozen:
    required[f"frozen constant {token}"] = token in policy

failures = [name for name, ok in required.items() if not ok]
if failures:
    for name in failures:
        print("FAIL", name)
    raise SystemExit(1)
print("DEV15_SESSION_BOUNDARY_CONTRACT_PASS")
