export const CRITICAL_CONTROL_KEYS=Object.freeze([
  'authority_view_v1','authority_ack_v1','calibration_meta_v10','calibration_ack_v10','decision_meta_v10','decision_ack_v10',
  'scenario_command_v1','scenario_ack_v1','run_start_prepare_v1','run_start_ready_v1','run_start_commit_v1',
  'run_freeze_prepare_v2','run_freeze_ready_v2','run_freeze_commit_v2',
] as const);
export const CRITICAL_CONTROL_BUDGET=Object.freeze({payloadBytes:600,frameBytes:900,datagramBytes:1200});
