#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
rust=ROOT/'crates/body-finder-science/src/human_detector.rs'
s=rust.read_text(encoding='utf-8')
s=s.replace('components.insert(\n        "distributed_motion_gate".into(),','components.insert("distributed_motion_gate".into(),')
rust.write_text(s,encoding='utf-8')
p=Path(__file__).with_name('apply_dev20_8_delta.py')
exec(compile(p.read_text(encoding='utf-8'),str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
