#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])).get('validation_run',{}); ok=r.get('snapshot_frozen') is True and 'geometry_at_end' in r and 'graph_diagnostics_at_end' in r
print(json.dumps({'pass':ok,'snapshot_frozen':r.get('snapshot_frozen'),'has_geometry_at_end':'geometry_at_end' in r},indent=2)); sys.exit(0 if ok else 1)
