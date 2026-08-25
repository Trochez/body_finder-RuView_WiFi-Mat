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
p.write_text(s)
print('apply_dev14 anchor/report hotfix PASS')
