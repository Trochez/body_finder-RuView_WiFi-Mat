from pathlib import Path
p=Path(__file__).with_name('apply_dev14.py')
s=p.read_text()
old="""# Both evaluation call sites end with trigger peer then closing parenthesis.\ncall_old='''        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),\\n      )'''\ncall_new='''        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(), ctx,\\n      )'''\nif n.count(call_old) < 2: raise SystemExit(f'environment call anchors missing: {n.count(call_old)}')\nn=n.replace(call_old,call_new)\n"""
new="""# Evaluation call sites have different indentation in diagnostics vs worker loop.\ncall_patterns = [\n('''        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),\\n      )''','''        BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(), ctx,\\n      )'''),\n('''              BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(),\\n            )''','''              BleAcquisitionPolicy.activeRecoveryGeneration(), BleAcquisitionPolicy.activeRecoveryTriggerKind(), BleAcquisitionPolicy.activeRecoveryTriggerPeerId(), ctx,\\n            )'''),\n]\nreplaced=0\nfor a,b in call_patterns:\n    if a in n:\n        n=n.replace(a,b)\n        replaced += 1\nif replaced < 2: raise SystemExit(f'environment call anchors missing: {replaced}')\n"""
if old not in s: raise SystemExit('hotfix anchor missing')
s=s.replace(old,new,1)
old_checker="checker=read('validation/android/check_dev13_environment_contract.py').replace('dev13','dev14').replace('experimental.13','experimental.14')"
new_checker="checker=read('validation/android/check_dev13_environment_contract.py').replace('dev13','dev14').replace('experimental.13','experimental.14').replace('reportVersion: 15','reportVersion: 16')"
if old_checker not in s: raise SystemExit('checker migration anchor missing')
s=s.replace(old_checker,new_checker,1)
old_schema="""env=schema['properties']['environment']; req=env.setdefault('required',[])\nfor x in ['total_background_ms','max_background_interval_ms','foreground_transition_count','unresolved_violation_count']:\n    if x not in req: req.append(x)\nwrite('protocol/schemas/validation-run-snapshot-v3.json',json.dumps(schema,indent=2)+'\\n')"""
new_schema="""env=schema['properties']['environment']\nenv.setdefault('properties',{}).update({\n    'total_background_ms': {'type':'integer','minimum':0},\n    'max_background_interval_ms': {'type':'integer','minimum':0},\n    'foreground_transition_count': {'type':'integer','minimum':0},\n    'unresolved_violation_count': {'type':'integer','minimum':0},\n    'environment_violation_events': {'type':'array'},\n})\n# Keep these dev14 additions optional: schema v3 must remain backward-compatible with dev13 snapshots.\nwrite('protocol/schemas/validation-run-snapshot-v3.json',json.dumps(schema,indent=2)+'\\n')"""
if old_schema not in s: raise SystemExit('schema compatibility anchor missing')
s=s.replace(old_schema,new_schema,1)
old_release="write('.github/workflows/release-exp14.yml',y)"
new_release="write('docs/generated-release-exp14.yml',y)\n# The validated YAML is installed into .github/workflows by the GitHub connector, because the Actions token cannot update workflow files."
if old_release not in s: raise SystemExit('release workflow output anchor missing')
s=s.replace(old_release,new_release,1)
p.write_text(s)
print('apply_dev14 anchor/report/schema/workflow hotfix PASS')
