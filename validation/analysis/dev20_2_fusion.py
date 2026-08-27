#!/usr/bin/env python3
"""Dev-20.2 deterministic multi-node human-presence fusion.

Ground truth is deliberately absent from this module. Inputs are calibrated BLE-RSSI
link samples and acquisition quality only. Missing/stale/weak topology fails closed.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
from math import exp, log1p, sqrt
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple
import json

ALGORITHM_VERSION = "deterministic-multinode-rssi-fusion-v2"
PARAMETERS = {
    "min_samples_per_link": 20,
    "min_observer_nodes": 2,
    "min_physical_baselines": 2,
    "max_alignment_span_ms": 12_000,
    "human_threshold": 1.05,
    "no_human_threshold": 0.42,
    "min_mean_quality": 0.45,
    "deviation_band_sigma": 2.5,
    "deviation_band_floor_db": 3.0,
    "feature_clip": 4.0,
}
PARAMETER_HASH = sha256(json.dumps(PARAMETERS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0

def variance(xs: Sequence[float]) -> float:
    if not xs: return 0.0
    m=mean(xs); return sum((x-m)**2 for x in xs)/len(xs)

def mad(xs: Sequence[float]) -> float:
    if not xs: return 0.0
    m=float(median(xs)); return float(median([abs(x-m) for x in xs]))

def percentile(xs: Sequence[float], p: float) -> float:
    if not xs: return 0.0
    s=sorted(xs); pos=(len(s)-1)*p; lo=int(pos); hi=min(len(s)-1,lo+1); f=pos-lo
    return s[lo]*(1-f)+s[hi]*f

def clip(x: float, hi: float|None=None) -> float:
    h=PARAMETERS["feature_clip"] if hi is None else hi
    return max(0.0,min(float(h),float(x)))

def sigmoid(x: float) -> float:
    x=max(-40.0,min(40.0,x)); return 1.0/(1.0+exp(-x))

def _values(samples: Sequence[Any]) -> List[float]:
    out=[]
    for s in samples:
        try:
            v=float(s.get("rssi_dbm") if isinstance(s,Mapping) else s)
            if -126 <= v <= 0: out.append(v)
        except Exception: pass
    return out

def _walls(samples: Sequence[Any]) -> List[int]:
    out=[]
    for s in samples:
        if isinstance(s,Mapping):
            try: out.append(int(s.get("wall_ms")))
            except Exception: pass
    return out

def _diff_energy(xs: Sequence[float]) -> float:
    return mean([(xs[i]-xs[i-1])**2 for i in range(1,len(xs))]) if len(xs)>1 else 0.0

def _slope_activity(xs: Sequence[float]) -> float:
    if len(xs)<4: return 0.0
    return mean([abs(xs[i]-xs[i-1]) for i in range(1,len(xs))])

@dataclass(frozen=True)
class LinkFeatureV2:
    link_id: str
    observer_node_id: str
    peer_id: str
    baseline_count: int
    sample_count: int
    baseline_median_dbm: float
    observation_median_dbm: float
    median_shift_z: float
    mean_shift_z: float
    baseline_mad_db: float
    observation_mad_db: float
    variance_ratio_change: float
    iqr_change_z: float
    derivative_energy_change: float
    slope_activity_change: float
    deviation_occupancy_change: float
    disturbance_persistence: float
    spectral_energy_proxy: float
    quality: float
    disturbance_score: float
    first_wall_ms: int|None
    last_wall_ms: int|None

@dataclass(frozen=True)
class FusionResultV2:
    prediction: str
    human_confidence: float
    evidence_quality: str
    fused_score: float
    contributing_links: int
    contributing_nodes: int
    physical_baselines: int
    reciprocal_pair_count: int
    simultaneous_disturbed_links: int
    reason: str
    component_scores: Dict[str,float]
    per_link_features: List[Dict[str,Any]]
    missing_or_stale_reasons: List[str]
    algorithm_version: str = ALGORITHM_VERSION
    parameter_hash: str = PARAMETER_HASH


def extract_link_features(link_id: str, baseline_samples: Sequence[Any], observation_samples: Sequence[Any]) -> LinkFeatureV2:
    b=_values(baseline_samples); o=_values(observation_samples)
    nmin=int(PARAMETERS["min_samples_per_link"])
    if len(b)<nmin or len(o)<nmin: raise ValueError(f"{link_id}: need >= {nmin} baseline/observation samples")
    bm=float(median(b)); om=float(median(o)); bs=max(1.0,1.4826*mad(b),sqrt(max(variance(b),0.0)))
    bvar=max(0.25,variance(b)); ovar=variance(o)
    biqr=percentile(b,.9)-percentile(b,.1); oiqr=percentile(o,.9)-percentile(o,.1)
    bde=max(.25,_diff_energy(b)); ode=_diff_energy(o)
    bsa=max(.25,_slope_activity(b)); osa=_slope_activity(o)
    band=max(float(PARAMETERS["deviation_band_floor_db"]),float(PARAMETERS["deviation_band_sigma"])*bs)
    bo=mean([1.0 if abs(x-bm)>=band else 0.0 for x in b]); oo=mean([1.0 if abs(x-bm)>=band else 0.0 for x in o])
    chunks=[o[i:i+max(5,len(o)//8)] for i in range(0,len(o),max(5,len(o)//8))]
    persistence=mean([1.0 if mean([1.0 if abs(x-bm)>=band else 0.0 for x in c])>=.20 else 0.0 for c in chunks]) if chunks else 0.0
    medz=clip(abs(om-bm)/bs); meanz=clip(abs(mean(o)-mean(b))/bs)
    vr=clip(log1p(abs(ovar-bvar)/bvar)); iqr=clip(abs(oiqr-biqr)/max(1.0,biqr))
    de=clip(log1p(abs(ode-bde)/bde)); sa=clip(log1p(abs(osa-bsa)/bsa)); occ=clip(max(0.0,oo-bo)*4.0)
    pscore=clip(persistence*2.0)
    score=.15*medz+.10*meanz+.16*vr+.10*iqr+.18*de+.10*sa+.13*occ+.08*pscore
    walls=_walls(observation_samples); observer,_,peer=link_id.partition("::")
    quality=min(1.0,min(len(b),len(o))/80.0)*(1.0 if bs<=12 else .6)
    return LinkFeatureV2(link_id,observer,peer,len(b),len(o),bm,om,medz,meanz,mad(b),mad(o),vr,iqr,de,sa,occ,persistence,ode,max(0.0,min(1.0,quality)),score,min(walls) if walls else None,max(walls) if walls else None)


def _physical_key(f: LinkFeatureV2) -> str:
    a=f.observer_node_id or "?"; b=f.peer_id or "?"; return "::".join(sorted((a,b)))

def infer_fused_presence(baseline_by_link: Mapping[str,Sequence[Any]], observation_by_link: Mapping[str,Sequence[Any]], *, acquisition_health: Mapping[str,Any]|None=None) -> FusionResultV2:
    reasons=[]; features=[]
    for lid in sorted(set(baseline_by_link)&set(observation_by_link)):
        try: features.append(extract_link_features(lid,baseline_by_link[lid],observation_by_link[lid]))
        except ValueError as e: reasons.append(str(e))
    health=dict(acquisition_health or {})
    if not bool(health.get("baseline_regression_pass",True)) or not bool(health.get("environment_valid",True)):
        return FusionResultV2("INDETERMINATE",0.0,"LOW",0.0,len(features),0,0,0,0,"acquisition/environment health gate failed",{},[asdict(f) for f in features],reasons)
    observers={f.observer_node_id for f in features if f.observer_node_id}
    physical={_physical_key(f) for f in features}
    first=[f.first_wall_ms for f in features if f.first_wall_ms is not None]; last=[f.last_wall_ms for f in features if f.last_wall_ms is not None]
    if first and last and max(first)-min(last)>int(PARAMETERS["max_alignment_span_ms"]): reasons.append("cross-node windows do not overlap sufficiently")
    q=mean([f.quality for f in features]) if features else 0.0
    if len(observers)<int(PARAMETERS["min_observer_nodes"]): reasons.append("fewer than two observer nodes contribute")
    if len(physical)<int(PARAMETERS["min_physical_baselines"]): reasons.append("fewer than two physical baselines contribute")
    if q<float(PARAMETERS["min_mean_quality"]): reasons.append("mean evidence quality below gate")
    if reasons and (len(observers)<2 or len(physical)<2 or q<float(PARAMETERS["min_mean_quality"]) or any("overlap" in r for r in reasons)):
        return FusionResultV2("INDETERMINATE",0.0,"LOW",0.0,len(features),len(observers),len(physical),0,0,"insufficient independent synchronized RF evidence",{"mean_link_quality":q},[asdict(f) for f in features],reasons)
    totalw=sum(max(.05,f.quality) for f in features); base=sum(f.disturbance_score*max(.05,f.quality) for f in features)/max(.01,totalw)
    by_phys: Dict[str,List[LinkFeatureV2]]={}
    for f in features: by_phys.setdefault(_physical_key(f),[]).append(f)
    reciprocal=[v for v in by_phys.values() if len(v)>=2]
    recip_agreement=mean([max(0.0,1.0-abs(v[0].disturbance_score-v[1].disturbance_score)/max(.5,max(v[0].disturbance_score,v[1].disturbance_score))) for v in reciprocal]) if reciprocal else 0.0
    disturbed=sum(1 for f in features if f.disturbance_score>=.9)
    cross_support=min(1.0,disturbed/max(2.0,float(len(features))))
    node_support=min(1.0,len(observers)/3.0); baseline_support=min(1.0,len(physical)/3.0)
    fused=base*(.72+.10*recip_agreement+.10*cross_support+.04*node_support+.04*baseline_support)
    components={"quality_weighted_link_score":base,"reciprocal_coherence":recip_agreement,"cross_link_support":cross_support,"observer_support":node_support,"physical_baseline_support":baseline_support,"mean_link_quality":q}
    p=max(.02,min(.98,sigmoid((fused-.72)*4.0)))
    eq="HIGH" if q>=.75 and len(observers)>=3 and len(physical)>=3 else "MEDIUM"
    if fused>=float(PARAMETERS["human_threshold"]): pred="HUMAN_EVIDENCE"; conf=p; reason="multi-node temporal/variance disturbance exceeds fused threshold"
    elif fused<=float(PARAMETERS["no_human_threshold"]): pred="NO_HUMAN_EVIDENCE"; conf=1-p; reason="multi-node evidence is compatible with calibrated background; not proof of absence"
    else: pred="INDETERMINATE"; conf=max(p,1-p); reason="fused disturbance is inside conservative decision band"
    return FusionResultV2(pred,conf,eq,fused,len(features),len(observers),len(physical),len(reciprocal),disturbed,reason,components,[asdict(f) for f in features],reasons)


def canonical_result(result: FusionResultV2) -> str:
    return json.dumps(asdict(result),sort_keys=True,separators=(",",":"),allow_nan=False)
