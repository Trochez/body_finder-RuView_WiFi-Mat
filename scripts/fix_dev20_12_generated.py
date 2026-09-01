#!/usr/bin/env python3
from pathlib import Path
p=Path('apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt')
s=p.read_text(encoding='utf-8')
# RangeFrameV9 is a frozen contract name; the wire message_type stays RANGE_FRAME.
if 'RANGE_FRAME_SCHEMA = "RangeFrameV9"' not in s:
    marker='private object WireTransportV10 {\n'
    if marker not in s: raise SystemExit('WireTransportV10 marker missing')
    s=s.replace(marker, marker+'  private const val RANGE_FRAME_SCHEMA = "RangeFrameV9"\n', 1)
p.write_text(s,encoding='utf-8')
print('dev20.12 generated fixes applied')
