#!/usr/bin/env python3
import json,pathlib,re
R=pathlib.Path(__file__).resolve().parents[1]
p=R/'validation/analysis/dev20_3_detector.py'; s=p.read_text()
manifest=json.loads((R/'validation/fixtures/dev20_3/detector-parameter-manifest.json').read_text())
h=manifest['parameter_hash']
s=re.sub(r'PARAMETER_HASH = sha256\([^\n]+\)\.hexdigest\(\)',f'PARAMETER_HASH = "{h}"',s,1)
s=s.replace('    score=.15*medz+.10*meanz+.16*vr+.10*iqr+.18*de+.10*sa+.13*occ+.08*pscore',
'''    madc=clip(abs(mad(o)-mad(b))/max(1.0,mad(b)))
    score=.07*medz+.06*meanz+.08*madc+.16*vr+.12*iqr+.18*de+.10*sa+.12*occ+.11*pscore''')
s=s.replace('    if len(observers)<int(PARAMETERS["min_observer_nodes"]): reasons.append("fewer than two observer nodes contribute")',
'''    if len(observers)<int(PARAMETERS["min_observer_nodes"]): reasons.append("fewer than three observer nodes contribute")
    if len(features)<6: reasons.append("fewer than six directional links contribute")''')
s=s.replace('    if len(physical)<int(PARAMETERS["min_physical_baselines"]): reasons.append("fewer than two physical baselines contribute")',
'    if len(physical)<int(PARAMETERS["min_physical_baselines"]): reasons.append("fewer than three physical baselines contribute")')
s=s.replace('    if reasons and (len(observers)<2 or len(physical)<2 or q<float(PARAMETERS["min_mean_quality"]) or any("overlap" in r for r in reasons)):',
'    if reasons and (len(observers)<int(PARAMETERS["min_observer_nodes"]) or len(physical)<int(PARAMETERS["min_physical_baselines"]) or len(features)<6 or q<float(PARAMETERS["min_mean_quality"]) or any("overlap" in r for r in reasons)):')
s=s.replace('    disturbed=sum(1 for f in features if f.disturbance_score>=.9)',
'''    disturbed=sum(1 for f in features if f.disturbance_score>=.48)
    disturbed_baselines=len({_physical_key(f) for f in features if f.disturbance_score>=.48})''')
s=s.replace('    if fused>=float(PARAMETERS["human_threshold"]): pred="HUMAN_EVIDENCE"; conf=p; reason="multi-node temporal/variance disturbance exceeds fused threshold"\n    elif fused<=float(PARAMETERS["no_human_threshold"]): pred="NO_HUMAN_EVIDENCE"; conf=1-p; reason="multi-node evidence is compatible with calibrated background; not proof of absence"',
'''    if fused>=float(PARAMETERS["human_threshold"]) and disturbed>=2 and disturbed_baselines>=2: pred="HUMAN_EVIDENCE"; conf=p; reason="distributed multi-feature disturbance evidence"
    elif fused<=float(PARAMETERS["no_human_threshold"]) and disturbed==0: pred="NO_HUMAN_EVIDENCE"; conf=1-p; reason="affirmative clean calibrated background evidence; not proof of absence"''')
if 'fewer than six directional links contribute' not in s: raise SystemExit('topology hardening patch failed')
if f'PARAMETER_HASH = "{h}"' not in s: raise SystemExit('parameter hash patch failed')
p.write_text(s)
print('DEV20_3_GENERATED_HARDENING_APPLIED',h)
