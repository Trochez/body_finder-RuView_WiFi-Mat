import json

def unwrap(doc):
    if isinstance(doc,dict) and isinstance(doc.get('validation_run'),dict): return doc['validation_run']
    if isinstance(doc,dict) and isinstance(doc.get('diagnostics'),dict) and isinstance(doc['diagnostics'].get('validation_run'),dict): return doc['diagnostics']['validation_run']
    if isinstance(doc,dict) and isinstance(doc.get('snapshot'),dict): return doc['snapshot']
    return doc if isinstance(doc,dict) else {}

def timeline_errors(doc):
    r=unwrap(doc); ev=r.get('events',[]) or []; errors=[]
    for key in ('seq','wall_ms'):
        vals=[e.get(key) for e in ev if isinstance(e.get(key),(int,float))]
        if vals != sorted(vals): errors.append('NON_MONOTONIC_'+key.upper())
    elapsed=[e.get('elapsed_from_run_start_ms',e.get('elapsed_ms')) for e in ev]
    elapsed=[x for x in elapsed if isinstance(x,(int,float))]
    if elapsed != sorted(elapsed): errors.append('NON_MONOTONIC_ELAPSED')
    by={}
    for e in ev:
        g=e.get('recovery_generation')
        if g is not None: by.setdefault(g,[]).append(e)
    for g,es in by.items():
        req=[e for e in es if e.get('type')=='RECOVERY_REQUESTED']; first=[e for e in es if e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY']
        suc=[e for e in es if e.get('type')=='RECOVERY_SUCCESS']; fail=[e for e in es if e.get('type')=='RECOVERY_FAILURE']; term=suc+fail
        if len(req)>1: errors.append('DUPLICATE_RECOVERY_REQUEST')
        if len(first)>1: errors.append('DUPLICATE_FIRST_VALID')
        if len(term)>1:
            errors.append('TERMINAL_CONTRADICTION' if suc and fail else 'DUPLICATE_TERMINAL')
        if suc and not first: errors.append('RECOVERY_SUCCESS_WITHOUT_FIRST_VALID')
        if suc and req and first:
            if not (req[0].get('seq',0)<first[0].get('seq',0)<suc[0].get('seq',0)): errors.append('RECOVERY_CAUSAL_ORDER_INVALID')
            if req[0].get('trigger_kind')=='PEER_STARVATION':
                target=req[0].get('trigger_peer_id') or req[0].get('peer_id')
                if first[0].get('peer_id')!=target or suc[0].get('peer_id')!=target: errors.append('FIRST_VALID_WRONG_TARGET')
        if term:
            terminal_seq=min(e.get('seq',0) for e in term)
            if any(e.get('type')=='FIRST_VALID_BF_CALLBACK_AFTER_RECOVERY' and e.get('seq',0)>terminal_seq for e in es): errors.append('CALLBACK_AFTER_TERMINAL')
    return list(dict.fromkeys(errors))

def environment_errors(doc):
    r=unwrap(doc); env=r.get('environment',{}) or {}; errors=[]
    types=list(env.get('violation_types',[]) or [])
    if 'RECOVERY_START_MISSING' in types: errors.append('RECOVERY_START_MISSING')
    if 'FILTERED_PROBE_WINDOW_EXPIRED' in types: errors.append('FILTERED_PROBE_WINDOW_EXPIRED')
    if env.get('valid') is False:
        if 'APP_NOT_FOREGROUND' in types: errors.append('APP_NOT_FOREGROUND')
        elif not errors: errors.append('ENVIRONMENT_INVALID')
    events=r.get('environment_violation_events',env.get('environment_violation_events',[])) or []
    active_by={}
    for e in sorted(events,key=lambda x:x.get('started_wall_ms',0)):
        t=e.get('type'); s=e.get('started_wall_ms'); z=e.get('resolved_wall_ms'); d=e.get('duration_ms')
        if not t or not isinstance(s,(int,float)) or not isinstance(d,(int,float)) or d<0: errors.append('ENVIRONMENT_INTERVAL_INVALID'); continue
        if z is not None and isinstance(z,(int,float)) and z-s != d: errors.append('ENVIRONMENT_INTERVAL_DURATION_MISMATCH')
        prev=active_by.get(t)
        if prev is not None and s < prev: errors.append('DUPLICATE_OVERLAPPING_ENVIRONMENT_INTERVAL')
        active_by[t]=z if isinstance(z,(int,float)) else float('inf')
    return list(dict.fromkeys(errors))

def hard_gate_errors(doc, acceptance=True):
    r=unwrap(doc); errors=[]
    if r.get('snapshot_schema_version') not in (None,3): errors.append('SNAPSHOT_SCHEMA_DRIFT')
    if r.get('snapshot_frozen') is not True: errors.append('SNAPSHOT_NOT_FROZEN')
    elapsed=r.get('elapsed_ms',r.get('snapshot_elapsed_ms',0)) or 0
    if acceptance and elapsed < 300000: errors.append('LONG_RUN_TOO_SHORT')
    pre=r.get('preflight_at_start',{}) or {}
    if pre and pre.get('ready') is not True: errors.append('PREFLIGHT_NOT_READY')
    env=r.get('environment',{}) or {}
    if env.get('valid') is not True: errors += environment_errors(r)
    if (env.get('unauthorized_strategy_violation_count',0) or 0)!=0: errors.append('UNAUTHORIZED_STRATEGY_VIOLATION')
    if (r.get('usable_metric_range_uptime_percent',100) or 0)<90: errors.append('USABLE_METRIC_UPTIME_LOW')
    if (r.get('geometry_2d_uptime_percent',100) or 0)<90: errors.append('GEOMETRY2D_UPTIME_LOW')
    counters=r.get('validation_counters',{}) or {}
    if (counters.get('peer_expire_delta',r.get('peer_expire_delta',0)) or 0)!=0: errors.append('PEER_EXPIRE_NONZERO')
    acq=r.get('acquisition_state_at_end',{}) or {}
    if (acq.get('recovery_attempts_in_current_5min_window',0) or 0)>3: errors.append('RECOVERY_BUDGET_EXCEEDED')
    if (acq.get('filtered_probe_window_ms',15000) or 15000)!=15000: errors.append('FILTERED_PROBE_HARD_LIMIT_DRIFT')
    if (acq.get('filtered_probe_exit_target_ms',14500) or 14500)>14500: errors.append('FILTERED_PROBE_EXIT_TARGET_DRIFT')
    errors += timeline_errors(r)
    errors += environment_errors(r)
    return list(dict.fromkeys(errors))
