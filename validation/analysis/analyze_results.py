#!/usr/bin/env python3
"""Analyze Body Finder dev-release JSON/JSONL files without external dependencies."""
import argparse, json, math, pathlib, statistics


def load_jsonl(path):
    out=[]
    for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines():
        try: out.append(json.loads(line))
        except json.JSONDecodeError: pass
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--truth-x', type=float)
    ap.add_argument('--truth-y', type=float)
    args=ap.parse_args()
    rows=[]
    for f in args.files:
        p=pathlib.Path(f)
        if p.suffix=='.jsonl': rows.extend(load_jsonl(p))
        else:
            obj=json.loads(p.read_text(encoding='utf-8'))
            rows.append({'human_estimate':obj.get('estimate'), 'node':obj.get('local'), 'peer_count':len(obj.get('peers',[])), 'source_file':str(p)})
    estimates=[r.get('human_estimate') for r in rows if r.get('human_estimate')]
    rssis=[]
    for r in rows:
        n=r.get('node') or {}
        if isinstance(n,dict) and isinstance(n.get('rssi_dbm'),(int,float)): rssis.append(float(n['rssi_dbm']))
    report={
      'rows':len(rows),
      'estimates':len(estimates),
      'estimate_rate':len(estimates)/max(1,len(rows)),
      'rssi_samples':len(rssis),
      'rssi_mean_dbm':statistics.mean(rssis) if rssis else None,
      'rssi_std_db':statistics.pstdev(rssis) if len(rssis)>1 else None,
      'quality_counts':{},
      'ground_truth':None,
    }
    for e in estimates: report['quality_counts'][e.get('evidence_quality') or e.get('quality','UNKNOWN')]=report['quality_counts'].get(e.get('evidence_quality') or e.get('quality','UNKNOWN'),0)+1
    if args.truth_x is not None and args.truth_y is not None and estimates:
        errors=[]; covered=0
        for e in estimates:
            x=e.get('x_m'); y=e.get('y_m'); rad=e.get('error_radius_95_m')
            if isinstance(x,(int,float)) and isinstance(y,(int,float)):
                err=math.hypot(x-args.truth_x,y-args.truth_y); errors.append(err)
                if isinstance(rad,(int,float)) and err<=rad: covered+=1
        if errors:
            report['ground_truth']={
              'x_m':args.truth_x,'y_m':args.truth_y,
              'mae_m':statistics.mean(errors),
              'rmse_m':math.sqrt(statistics.mean([e*e for e in errors])),
              'median_error_m':statistics.median(errors),
              'p95_region_coverage':covered/len(errors),
              'n':len(errors)
            }
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__': main()
