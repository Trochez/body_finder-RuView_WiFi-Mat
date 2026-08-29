import { requireNativeModule } from 'expo-modules-core';

export type NativeApi = {
  getCapabilitiesJson(): string; getDiagnosticsJson(): string; shareJsonFile(json: string, filename: string): boolean;
  evaluateHumanPresenceJson(inputJson: string): string;
  getWifiRssi(): number | null; updateLocalState(baseline: number | null, sigma: number | null, scanning: boolean): boolean;
  updatePublishedGeometry(publish: boolean, geometryJson: string | null): boolean; updateGeometryState(geometryState: string): boolean;
  updateValidationTruthJson(truthJson: string): boolean; updateAppVisibility(visibility: string): boolean; startValidationRun(): string;
  endValidationRun(): boolean; getValidationRunJson(): string; getCompletedValidationRunsSummaryJson(): string;
  selectValidationRun(runId: string): boolean; getCalibrationSnapshotJson(): string;
  startFabric(nodeId: string | null, displayName: string | null, sessionId: string | null): Promise<boolean>; stopFabric(): boolean;
  getPeersJson(): string; getLocalAdvertisementJson(): string;
};
const native = requireNativeModule<NativeApi>('BodyFinderNative');
const ACCEPTANCE_MINIMUM_MS=330_000;
function sanitizeCalibrationSnapshotJson(raw:string):string{try{const value=JSON.parse(raw);const walk=(node:any):any=>{if(Array.isArray(node))return node.map(walk);if(!node||typeof node!=='object')return node;const out:any={};for(const [key,child] of Object.entries(node)){if(key==='rssi_samples_dbm'&&Array.isArray(child))out[key]=child.filter(sample=>typeof sample==='number'&&Number.isFinite(sample)&&sample!==127&&sample>=-127&&sample<=20);else out[key]=walk(child);}return out;};return JSON.stringify(walk(value));}catch{return raw;}}
function upgradeValidationContract(raw:string):string{try{const d=JSON.parse(raw);const v=d?.validation_run??d;if(v&&typeof v==='object'){const elapsed=Number(v.elapsed_ms??v.snapshot_elapsed_ms??0);v.acceptance_minimum_ms=ACCEPTANCE_MINIMUM_MS;v.acceptance_duration_eligible=elapsed>=ACCEPTANCE_MINIMUM_MS;v.short_diagnostic_run=elapsed>0&&elapsed<ACCEPTANCE_MINIMUM_MS;v.evidence_contract_version='dev20.5-self-contained-json-evidence-v8';}if(Array.isArray(d?.completed_validation_runs_summary))for(const v of d.completed_validation_runs_summary){const elapsed=Number(v?.elapsed_ms??0);v.acceptance_minimum_ms=ACCEPTANCE_MINIMUM_MS;v.acceptance_duration_eligible=elapsed>=ACCEPTANCE_MINIMUM_MS;v.short_diagnostic_run=elapsed>0&&elapsed<ACCEPTANCE_MINIMUM_MS;}return JSON.stringify(d);}catch{return raw;}}
function upgradeExport(raw:string):string{try{const d=JSON.parse(raw);d.evidence_contract={...(d.evidence_contract??{}),schema:'dev20.5-self-contained-json-evidence-v8',screenshots_required:false,json_self_contained:true,required_external_input:'ground_truth_and_scenario_metadata_only_for_final_validator',diagnostic_source:'this JSON export'};d.acceptance_minimum_ms=ACCEPTANCE_MINIMUM_MS;d.human_localization_validated=false;d.rescue_use_validated=false;if(d.validation_run){const elapsed=Number(d.validation_run.elapsed_ms??0);d.validation_run.acceptance_minimum_ms=ACCEPTANCE_MINIMUM_MS;d.validation_run.acceptance_duration_eligible=elapsed>=ACCEPTANCE_MINIMUM_MS;d.validation_run.short_diagnostic_run=elapsed>0&&elapsed<ACCEPTANCE_MINIMUM_MS;d.validation_run.evidence_contract_version='dev20.5-self-contained-json-evidence-v8';}return JSON.stringify(d,null,2);}catch{return raw;}}
const api:NativeApi={...native,getDiagnosticsJson:()=>upgradeValidationContract(native.getDiagnosticsJson()),getValidationRunJson:()=>upgradeValidationContract(native.getValidationRunJson()),getCompletedValidationRunsSummaryJson:()=>upgradeValidationContract(native.getCompletedValidationRunsSummaryJson()),getCalibrationSnapshotJson:()=>sanitizeCalibrationSnapshotJson(native.getCalibrationSnapshotJson()),shareJsonFile:(json,filename)=>native.shareJsonFile(upgradeExport(json),filename)};
export default api;
