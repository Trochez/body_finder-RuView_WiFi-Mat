#!/usr/bin/env python3
"""Deterministic, dependency-free scientific baselines for Body Finder dev20+.

The module intentionally separates evidence processing from release claims. It
can produce HUMAN_EVIDENCE / NO_HUMAN_EVIDENCE / INDETERMINATE, deterministic RTI
localization with covariance, conservative tracking, and stratified metrics. It
never treats replay as live physical proof and never infers survivability.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import exp, hypot, sqrt
from statistics import median
from typing import Any, Dict, List, Mapping, Sequence, Tuple

EPS = 1e-9


def _finite(x: Any) -> bool:
    try:
        return float(x) == float(x) and abs(float(x)) != float("inf")
    except Exception:
        return False


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def variance(xs: Sequence[float], center: float | None = None) -> float:
    if not xs:
        return 0.0
    c = mean(xs) if center is None else center
    return sum((x - c) ** 2 for x in xs) / len(xs)


def mad(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    m = median(xs)
    return float(median([abs(x - m) for x in xs]))


def sigmoid(x: float) -> float:
    if x >= 40:
        return 1.0
    if x <= -40:
        return 0.0
    return 1.0 / (1.0 + exp(-x))


@dataclass(frozen=True)
class LinkFeatures:
    link_id: str
    sample_count: int
    baseline_count: int
    baseline_median_dbm: float
    observation_median_dbm: float
    delta_db: float
    baseline_mad_db: float
    observation_mad_db: float
    rolling_variance: float
    normalized_change: float
    spectral_energy_proxy: float
    quality: float


@dataclass(frozen=True)
class PresenceResult:
    prediction: str
    human_confidence: float
    evidence_quality: str
    aggregate_change_score: float
    contributing_links: int
    feature_provenance: List[Dict[str, Any]]
    reason: str
    algorithm_version: str = "deterministic-rssi-change-v1"


@dataclass(frozen=True)
class LocalizationResult:
    status: str
    x_m: float | None
    y_m: float | None
    covariance_2x2: List[List[float]] | None
    error_radius_95_m: float | None
    localization_tier: str
    grid_step_m: float
    support_links: int
    reason: str
    method: str = "deterministic-rti-segment-v1"


@dataclass
class Track:
    track_id: str
    x_m: float
    y_m: float
    covariance_2x2: List[List[float]]
    state: str = "PROBABLE_HUMAN"
    age_frames: int = 1
    missed_frames: int = 0
    last_frame: int = 0


def extract_link_features(link_id: str, baseline_values: Sequence[float], observed_values: Sequence[float]) -> LinkFeatures:
    b = [float(x) for x in baseline_values if _finite(x)]
    o = [float(x) for x in observed_values if _finite(x)]
    if len(b) < 3 or len(o) < 3:
        raise ValueError(f"{link_id}: at least 3 baseline and observation samples are required")
    bmed = float(median(b)); omed = float(median(o))
    bmad = mad(b); omad = mad(o)
    robust_sigma = max(1.0, 1.4826 * bmad, sqrt(max(variance(b), 0.0)))
    delta = omed - bmed
    normalized = min(25.0, abs(delta) / robust_sigma)
    spectral = mean([(o[i] - o[i-1]) ** 2 for i in range(1, len(o))]) if len(o) > 1 else 0.0
    quality = min(1.0, min(len(b), len(o)) / 20.0) * (1.0 if robust_sigma <= 12.0 else 0.6)
    return LinkFeatures(link_id, len(o), len(b), bmed, omed, delta, bmad, omad, variance(o), normalized, spectral,
                        max(0.0, min(1.0, quality)))


def infer_presence(baseline_by_link: Mapping[str, Sequence[float]], observation_by_link: Mapping[str, Sequence[float]], *,
                   acquisition_health: Mapping[str, Any] | None = None, min_links: int = 2,
                   indeterminate_quality_below: float = 0.35, human_threshold: float = 1.65,
                   no_human_threshold: float = 0.85) -> PresenceResult:
    features: List[LinkFeatures] = []
    for link_id in sorted(set(baseline_by_link) & set(observation_by_link)):
        try:
            features.append(extract_link_features(link_id, baseline_by_link[link_id], observation_by_link[link_id]))
        except ValueError:
            continue
    health = dict(acquisition_health or {})
    acquisition_ok = bool(health.get("baseline_regression_pass", True)) and bool(health.get("environment_valid", True))
    weighted = [(f.normalized_change, max(0.05, f.quality)) for f in features]
    total_w = sum(w for _, w in weighted)
    aggregate = sum(v*w for v, w in weighted) / total_w if total_w else 0.0
    link_quality = mean([f.quality for f in features]) if features else 0.0
    uptime = float(health.get("usable_metric_range_uptime_percent", 100.0) or 0.0) / 100.0
    evidence_score = min(1.0, link_quality * max(0.0, min(1.0, uptime)))
    prov = [asdict(f) for f in features]
    if not acquisition_ok:
        return PresenceResult("INDETERMINATE", 0.0, "LOW", aggregate, len(features), prov,
                              "acquisition/environment health gate failed")
    if len(features) < min_links or evidence_score < indeterminate_quality_below:
        return PresenceResult("INDETERMINATE", 0.0, "LOW", aggregate, len(features), prov,
                              "insufficient independent RF evidence")
    evidence_quality = "HIGH" if evidence_score >= 0.75 and len(features) >= 4 else "MEDIUM"
    p = max(0.05, min(0.95, 0.05 + 0.90 * sigmoid((aggregate - 1.25) * 2.2)))
    if aggregate >= human_threshold:
        return PresenceResult("HUMAN_EVIDENCE", p, evidence_quality, aggregate, len(features), prov,
                              "multi-link background change exceeds deterministic threshold")
    if aggregate <= no_human_threshold:
        return PresenceResult("NO_HUMAN_EVIDENCE", 1.0-p, evidence_quality, aggregate, len(features), prov,
                              "evidence is compatible with calibrated background; this is not proof of absence")
    return PresenceResult("INDETERMINATE", max(p, 1-p), evidence_quality, aggregate, len(features), prov,
                          "disturbance falls inside conservative decision band")


def _distance_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx-ax, by-ay
    denom = dx*dx + dy*dy
    if denom <= EPS:
        return hypot(px-ax, py-ay)
    t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy)/denom))
    return hypot(px-(ax+t*dx), py-(ay+t*dy))


def localize_rti(feature_by_link: Mapping[str, Mapping[str, Any] | LinkFeatures], sensor_positions: Mapping[str, Sequence[float]],
                 link_endpoints: Mapping[str, Sequence[str]], *, grid_step_m: float = 0.5, margin_m: float = 1.0,
                 min_support_links: int = 3) -> LocalizationResult:
    usable: List[Tuple[str, float, float, Tuple[float,float], Tuple[float,float]]] = []
    for link_id in sorted(feature_by_link):
        ep = link_endpoints.get(link_id)
        if not ep or len(ep) != 2 or ep[0] not in sensor_positions or ep[1] not in sensor_positions:
            continue
        f = feature_by_link[link_id]
        change = float(f.normalized_change if isinstance(f, LinkFeatures) else f.get("normalized_change", 0.0))
        quality = float(f.quality if isinstance(f, LinkFeatures) else f.get("quality", 0.0))
        if change < 0.75 or quality <= 0.0:
            continue
        a = sensor_positions[ep[0]]; b = sensor_positions[ep[1]]
        usable.append((link_id, change, quality, (float(a[0]),float(a[1])), (float(b[0]),float(b[1]))))
    if len(usable) < min_support_links:
        return LocalizationResult("WITHHELD", None, None, None, None, "PRESENCE_ONLY", grid_step_m, len(usable),
                                  "insufficient link diversity for a defensible point estimate")
    xs=[float(p[0]) for p in sensor_positions.values()]; ys=[float(p[1]) for p in sensor_positions.values()]
    minx,maxx=min(xs)-margin_m,max(xs)+margin_m; miny,maxy=min(ys)-margin_m,max(ys)+margin_m
    cells: List[Tuple[float,float,float]]=[]
    ix=0; x=minx
    while x <= maxx + grid_step_m*0.25 and ix < 200:
        iy=0; y=miny
        while y <= maxy + grid_step_m*0.25 and iy < 200:
            score=0.0
            for _,change,q,a,b in usable:
                d=_distance_point_to_segment(x,y,a[0],a[1],b[0],b[1])
                score += q * change * exp(-(d*d)/(2*0.9*0.9))
            cells.append((x,y,score)); y += grid_step_m; iy += 1
        x += grid_step_m; ix += 1
    cells.sort(key=lambda c:(-c[2],c[0],c[1]))
    if not cells or cells[0][2] <= EPS:
        return LocalizationResult("WITHHELD",None,None,None,None,"PRESENCE_ONLY",grid_step_m,len(usable),"no stable RTI peak")
    peak=cells[0][2]; selected=[c for c in cells if c[2] >= peak*0.45][:80]
    weights=[exp((c[2]/max(peak,EPS))*3.0) for c in selected]; sw=sum(weights)
    mx=sum(c[0]*w for c,w in zip(selected,weights))/sw; my=sum(c[1]*w for c,w in zip(selected,weights))/sw
    cxx=sum(w*(c[0]-mx)**2 for c,w in zip(selected,weights))/sw + grid_step_m**2/12
    cyy=sum(w*(c[1]-my)**2 for c,w in zip(selected,weights))/sw + grid_step_m**2/12
    cxy=sum(w*(c[0]-mx)*(c[1]-my) for c,w in zip(selected,weights))/sw
    tr=cxx+cyy; det=max(0.0,cxx*cyy-cxy*cxy); disc=max(0.0,tr*tr-4*det); lam=max(EPS,(tr+sqrt(disc))/2)
    r95=2.448*sqrt(lam)
    tier="USABLE" if r95 <= 2.0 else "COARSE" if r95 <= 4.0 else "PRESENCE_ONLY"
    if tier == "PRESENCE_ONLY":
        return LocalizationResult("WITHHELD",None,None,[[cxx,cxy],[cxy,cyy]],r95,tier,grid_step_m,len(usable),
                                  "uncertainty exceeds safe point-estimate threshold")
    return LocalizationResult("ESTIMATE",mx,my,[[cxx,cxy],[cxy,cyy]],r95,tier,grid_step_m,len(usable),"deterministic RTI estimate")


def confusion_metrics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    tp=tn=fp=fn=ind=0
    for row in rows:
        truth=row.get("ground_truth"); pred=row.get("prediction")
        if pred == "INDETERMINATE": ind += 1; continue
        positive = truth == "HUMAN_PRESENT"; predicted = pred == "HUMAN_EVIDENCE"
        if positive and predicted: tp += 1
        elif positive: fn += 1
        elif predicted: fp += 1
        else: tn += 1
    def div(a:float,b:float): return a/b if b else None
    return {"tp":tp,"tn":tn,"fp":fp,"fn":fn,"indeterminate":ind,"precision":div(tp,tp+fp),"recall":div(tp,tp+fn),
            "specificity":div(tn,tn+fp),"f1":div(2*tp,2*tp+fp+fn),"false_positive_rate":div(fp,fp+tn),
            "decided_count":tp+tn+fp+fn,"total":len(rows)}


def brier_score(rows: Sequence[Mapping[str, Any]]) -> float | None:
    vals=[]
    for row in rows:
        if row.get("ground_truth") not in ("HUMAN_PRESENT","EMPTY") or not _finite(row.get("human_probability")):
            continue
        y=1.0 if row["ground_truth"]=="HUMAN_PRESENT" else 0.0; p=max(0.0,min(1.0,float(row["human_probability"])))
        vals.append((p-y)**2)
    return mean(vals) if vals else None


def enforce_split_policy(sessions: Sequence[Mapping[str, Any]]) -> None:
    by_id: Dict[str,set[str]]={}
    for s in sessions:
        sid=str(s.get("session_id","")); split=str(s.get("split",""))
        if not sid or split not in {"TRAIN","VALIDATION","TEST"}:
            raise ValueError("every session requires session_id and TRAIN/VALIDATION/TEST split")
        by_id.setdefault(sid,set()).add(split)
    leaked={sid:sorted(v) for sid,v in by_id.items() if len(v)>1}
    if leaked: raise ValueError(f"physical-session leakage detected: {leaked}")
    if any(s.get("split")=="TEST" and s.get("used_for_model_selection") for s in sessions):
        raise ValueError("final TEST sessions cannot be used for model selection")


def evaluate_presence_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    enforce_split_policy(rows); test=[r for r in rows if r.get("split")=="TEST"]
    if not test: raise ValueError("at least one frozen TEST session is required")
    overall=confusion_metrics(test)
    scenario={n:confusion_metrics([r for r in test if str(r.get("scenario","UNKNOWN"))==n]) for n in sorted({str(r.get("scenario","UNKNOWN")) for r in test})}
    devices={d:confusion_metrics([r for r in test if str(r.get("device_id","UNKNOWN"))==d]) for d in sorted({str(r.get("device_id","UNKNOWN")) for r in test})}
    return {"overall":overall,"by_scenario":scenario,"held_out_device_report":devices,"brier_score":brier_score(test)}


def track_localizations(frames: Sequence[Mapping[str, Any]], *, gate_m: float = 2.5, max_missed: int = 2) -> Dict[str, Any]:
    tracks: List[Track]=[]; next_id=1; history=[]; reacquired=0
    for frame_index, frame in enumerate(frames):
        dets=list(frame.get("detections",[]))
        if frame.get("unresolved_multi_target") and len(dets)>=2:
            history.append({"frame":frame_index,"state":"POSSIBLE_CLUSTER","member_count_estimate":len(dets),"tracks":[]})
            for t in tracks: t.missed_frames += 1; t.state="LOST"
            continue
        unmatched=set(range(len(dets)))
        for t in sorted(tracks,key=lambda z:z.track_id):
            candidates=[]
            for j in unmatched:
                d=dets[j]; dist=hypot(float(d["x_m"])-t.x_m,float(d["y_m"])-t.y_m)
                if dist <= gate_m: candidates.append((dist,j))
            if candidates:
                _,j=min(candidates); unmatched.remove(j); d=dets[j]
                if t.state=="LOST": reacquired += 1; t.state="REACQUIRED"
                else: t.state="CONFIRMED_TRACK" if t.age_frames>=2 else "PROBABLE_HUMAN"
                t.x_m=float(d["x_m"]); t.y_m=float(d["y_m"]); t.covariance_2x2=d.get("covariance_2x2",t.covariance_2x2)
                t.age_frames+=1; t.missed_frames=0; t.last_frame=frame_index
            else:
                t.missed_frames+=1; t.state="LOST"; t.covariance_2x2=[[t.covariance_2x2[0][0]+0.5,t.covariance_2x2[0][1]],[t.covariance_2x2[1][0],t.covariance_2x2[1][1]+0.5]]
        for j in sorted(unmatched):
            d=dets[j]; tracks.append(Track(f"T{next_id:03d}",float(d["x_m"]),float(d["y_m"]),d.get("covariance_2x2",[[1.0,0.0],[0.0,1.0]]),last_frame=frame_index)); next_id+=1
        tracks=[t for t in tracks if t.missed_frames <= max_missed]
        history.append({"frame":frame_index,"state":"TRACKS","tracks":[asdict(t) for t in tracks]})
    return {"timeline":history,"track_count_created":next_id-1,"id_switches":0,"fragmentation":max(0,next_id-2),
            "reacquisition_count":reacquired,"algorithm_version":"nearest-neighbor-conservative-v1"}


def capability_truth_from_probe(probe: Mapping[str, Any]) -> Dict[str, Any]:
    modality=str(probe.get("modality","UNKNOWN")); attempted=bool(probe.get("functional_probe_attempted")); samples=int(probe.get("real_sample_count",0) or 0)
    replay=bool(probe.get("replay",False)); supported=bool(probe.get("api_supported",False))
    state="REPLAY_ONLY" if replay else "VERIFIED_REAL" if attempted and samples>0 else "SUPPORTED_UNVERIFIED" if supported else "UNAVAILABLE"
    return {"modality":modality,"state":state,"functional_probe_attempted":attempted,"real_sample_count":samples,
            "model_name_whitelist_used":False,"detail":str(probe.get("detail",""))}


def aggregate_v1_reports(reports: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    required=("dev19","dev20","dev21","dev22","dev23","dev24"); missing=[k for k in required if k not in reports]; blockers=[]
    if missing: blockers.append("missing milestone reports: "+",".join(missing))
    if reports.get("dev19",{}).get("baseline_regression") != "PASS": blockers.append("dev19 acquisition regression not PASS")
    if reports.get("dev20",{}).get("physical_acceptance") != "PASS": blockers.append("dev20 physical human-presence acceptance not PASS")
    if reports.get("dev21",{}).get("physical_acceptance") != "PASS": blockers.append("dev21 localization acceptance not PASS")
    if reports.get("dev22",{}).get("physical_acceptance") != "PASS": blockers.append("dev22 tracking acceptance not PASS")
    if reports.get("dev24",{}).get("physical_acceptance") != "PASS": blockers.append("dev24 through-wall/parity acceptance not PASS")
    if reports.get("dev21",{}).get("location_without_uncertainty") is True: blockers.append("location emitted without uncertainty")
    if reports.get("dev23",{}).get("fabricated_csi") is True: blockers.append("unsupported CSI reported as real")
    return {"schema_version":1,"release":"v1-candidate","dev19_acquisition":"PASS" if reports.get("dev19",{}).get("baseline_regression")=="PASS" else "FAIL",
            "final_go":not blockers,"blockers":blockers,"rescue_use_validated":False,"rule":"final_go never implies rescue_use_validated"}
