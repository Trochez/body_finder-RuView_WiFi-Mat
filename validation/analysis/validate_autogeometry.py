#!/usr/bin/env python3
"""Validate Body Finder protocol-v2 field exports against external ground truth.

Standard-library only. Ground truth is read from a separate validation file and is
never part of the production solver. The validator aligns the solver's arbitrary
2-D gauge to the external frame using its anchor/axis and tries both mirror signs.
"""
import argparse
import json
import math
import statistics
from pathlib import Path


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def percentile(values, q):
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def obj_time_ms(obj, fallback):
    value = obj.get("unix_ms")
    if isinstance(value, (int, float)):
        return float(value)
    for key in ("generated_at_ms", "timestamp_ms"):
        value = obj.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return float(fallback)


def add_candidate(out, source, geometry, target, obj, sequence):
    if isinstance(geometry, dict):
        out.append({
            "source": source,
            "geometry": geometry,
            "target": target if isinstance(target, dict) else None,
            "obj": obj,
            "sequence": sequence,
            "time_ms": obj_time_ms(obj, sequence * 1000),
        })


def read_candidates(directory):
    out = []
    sequence = 0
    for p in sorted(directory.glob("*.json")):
        if p.name in {"ground-truth.json", "validation-summary.json"}:
            continue
        obj = load_json(p)
        if not isinstance(obj, dict):
            continue
        sequence += 1
        add_candidate(out, p.name, obj.get("geometry"), obj.get("estimate_array_frame"), obj, sequence)
    for p in sorted(directory.glob("*.jsonl")):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            sequence += 1
            add_candidate(out, f"{p.name}:{i + 1}", obj.get("geometry"), obj.get("human_estimate"), obj, sequence)
    return out


def geometry_rank(state):
    return {"GEOMETRY_2D": 4, "GEOMETRY_DEGRADED": 3, "GEOMETRY_1D": 2, "GEOMETRY_INSUFFICIENT": 1}.get(state, 0)


def choose_candidate(xs):
    if not xs:
        return None
    return max(xs, key=lambda x: (
        geometry_rank(x["geometry"].get("state", "")),
        len(x["geometry"].get("positions") or []),
        len(x["geometry"].get("used_edges") or []),
        x["geometry"].get("revision") or 0,
        x["sequence"],
    ))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def rmse(xs):
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else None


def position_map(g):
    return {
        p.get("node_id"): (float(p.get("x_m", 0)), float(p.get("y_m", 0)))
        for p in g.get("positions") or []
        if p.get("node_id")
    }


def position_record_map(g):
    return {p.get("node_id"): p for p in g.get("positions") or [] if p.get("node_id")}


def transform_factory(g, truth, sign):
    pm = position_map(g)
    a = g.get("anchor_node_id")
    b = g.get("axis_node_id")
    if not a or not b or a not in pm or b not in pm or a not in truth or b not in truth:
        return None
    ga, gb = pm[a], pm[b]
    ta, tb = truth[a], truth[b]
    ev = (gb[0] - ga[0], gb[1] - ga[1])
    tv = (tb[0] - ta[0], tb[1] - ta[1])
    el, tl = math.hypot(*ev), math.hypot(*tv)
    if el < 1e-9 or tl < 1e-9:
        return None
    eu = (ev[0] / el, ev[1] / el)
    en = (-eu[1], eu[0])
    tu = (tv[0] / tl, tv[1] / tl)
    tn = (-tu[1], tu[0])

    def transform(p):
        dx, dy = p[0] - ga[0], p[1] - ga[1]
        x = dx * eu[0] + dy * eu[1]
        y = dx * en[0] + dy * en[1]
        return (ta[0] + x * tu[0] + sign * y * tn[0], ta[1] + x * tu[1] + sign * y * tn[1])

    return transform


def observations_from_obj(obj):
    ranges = []
    if isinstance(obj.get("range_observations"), list):
        ranges.extend(obj["range_observations"])
    for key in ("node", "local"):
        value = obj.get(key)
        if isinstance(value, dict) and isinstance(value.get("ranges"), list):
            ranges.extend(value["ranges"])
    if isinstance(obj.get("all_nodes"), list):
        for node in obj["all_nodes"]:
            if isinstance(node, dict) and isinstance(node.get("ranges"), list):
                ranges.extend(node["ranges"])
    return [r for r in ranges if isinstance(r, dict)]


def temporal_metrics(xs):
    result = {}
    if not xs:
        return result
    ordered = sorted(xs, key=lambda x: (x["time_ms"], x["sequence"]))
    start = ordered[0]["time_ms"]
    solved = [x for x in ordered if x["geometry"].get("state") in {"GEOMETRY_2D", "GEOMETRY_DEGRADED"}]
    if solved:
        result["geometry_convergence_time_s"] = max(0.0, (solved[0]["time_ms"] - start) / 1000.0)
    state_counts = {}
    for x in ordered:
        state = x["geometry"].get("state", "UNKNOWN")
        state_counts[state] = state_counts.get(state, 0) + 1
    result["geometry_state_sample_counts"] = state_counts

    # Jitter is only meaningful while the deterministic frame ID is unchanged.
    frame_groups = {}
    for x in solved:
        frame = x["geometry"].get("frame_id")
        if frame:
            frame_groups.setdefault(frame, []).append(x)
    if frame_groups:
        frame, samples = max(frame_groups.items(), key=lambda item: len(item[1]))
        by_node = {}
        for x in samples:
            for node_id, p in position_map(x["geometry"]).items():
                by_node.setdefault(node_id, []).append(p)
        jitter = {}
        for node_id, points in by_node.items():
            if len(points) < 2:
                continue
            mx = statistics.fmean(p[0] for p in points)
            my = statistics.fmean(p[1] for p in points)
            radial = [math.hypot(p[0] - mx, p[1] - my) for p in points]
            jitter[node_id] = {
                "samples": len(points),
                "radial_rms_m": rmse(radial),
                "radial_p95_m": percentile(radial, 0.95),
                "radial_max_m": max(radial),
            }
        result["stationary_jitter_frame_id"] = frame
        result["stationary_node_jitter"] = jitter
    return result


def validate(directory, gt):
    xs = read_candidates(directory)
    chosen = choose_candidate(xs)
    result = {
        "input_directory": str(directory),
        "candidate_count": len(xs),
        "protocol_versions": sorted({str(
            x["obj"].get("protocol_version")
            or (x["obj"].get("node") or {}).get("protocol_version")
            or (x["obj"].get("local") or {}).get("protocol_version")
            or ""
        ) for x in xs}),
        "manual_geometry_override_violations": [],
    }
    result.update(temporal_metrics(xs))

    all_observations = []
    for x in xs:
        obj = x["obj"]
        vals = [
            obj.get("manual_geometry_override"),
            (obj.get("local") or {}).get("manual_geometry_override") if isinstance(obj.get("local"), dict) else None,
            (obj.get("node") or {}).get("manual_geometry_override") if isinstance(obj.get("node"), dict) else None,
        ]
        if any(v is True for v in vals):
            result["manual_geometry_override_violations"].append(x["source"])
        all_observations.extend(observations_from_obj(obj))

    technologies = sorted({r.get("technology") for r in all_observations if r.get("technology")})
    result["range_technologies"] = technologies
    result["range_observation_samples"] = len(all_observations)
    tech_counts = {}
    for r in all_observations:
        tech = r.get("technology") or "UNKNOWN"
        tech_counts[tech] = tech_counts.get(tech, 0) + 1
    result["range_observation_samples_by_technology"] = tech_counts

    if not chosen:
        result["error"] = "No geometry solution found in JSON/JSONL inputs"
        return result

    src, g, target = chosen["source"], chosen["geometry"], chosen["target"]
    solved_nodes = len(g.get("positions") or [])
    possible_edges = solved_nodes * (solved_nodes - 1) // 2
    used_edges = len(g.get("used_edges") or [])
    result.update({
        "selected_source": src,
        "geometry_state": g.get("state"),
        "dimension": g.get("dimension"),
        "frame_id": g.get("frame_id"),
        "revision": g.get("revision"),
        "solved_nodes": solved_nodes,
        "used_edges": used_edges,
        "rejected_edges": len(g.get("rejected_edges") or []),
        "residual_rms_m": g.get("residual_rms_m"),
        "condition_score": g.get("condition_score"),
        "possible_pair_edges_for_solved_nodes": possible_edges,
        "used_edge_availability_fraction": (used_edges / possible_edges) if possible_edges else None,
    })

    truth_raw = gt.get("node_positions_m") or {}
    truth = {k: (float(v[0]), float(v[1])) for k, v in truth_raw.items() if isinstance(v, list) and len(v) >= 2}
    pm = position_map(g)
    records = position_record_map(g)
    common = sorted(set(pm) & set(truth))
    result["ground_truth_common_nodes"] = common

    if len(common) >= 2:
        pair_errors = []
        for i, a in enumerate(common):
            for b in common[i + 1:]:
                pair_errors.append(dist(pm[a], pm[b]) - dist(truth[a], truth[b]))
        result["pairwise_distance_rmse_m"] = rmse(pair_errors)
        result["pairwise_distance_mean_abs_error_m"] = statistics.fmean(abs(x) for x in pair_errors) if pair_errors else None
        result["pairwise_distance_p95_abs_error_m"] = percentile([abs(x) for x in pair_errors], 0.95)
        result["pairwise_distance_max_abs_error_m"] = max((abs(x) for x in pair_errors), default=None)

    best = None
    for sign in (1, -1):
        f = transform_factory(g, truth, sign)
        if not f:
            continue
        errors = [dist(f(pm[n]), truth[n]) for n in common]
        score = rmse(errors)
        if best is None or (score is not None and score < best[0]):
            best = (score, sign, f, errors)

    if best:
        score, sign, f, errors = best
        result["alignment_mirror_sign"] = sign
        result["node_position_rmse_m"] = score
        result["node_position_mean_error_m"] = statistics.fmean(errors) if errors else None
        result["node_position_median_error_m"] = statistics.median(errors) if errors else None
        result["node_position_p95_error_m"] = percentile(errors, 0.95)
        result["node_position_max_error_m"] = max(errors) if errors else None

        covered = 0
        eligible = 0
        per_node = {}
        for node_id in common:
            aligned = f(pm[node_id])
            error = dist(aligned, truth[node_id])
            radius = records.get(node_id, {}).get("error_radius_95_m")
            inside = None
            if isinstance(radius, (int, float)) and math.isfinite(float(radius)):
                eligible += 1
                inside = error <= float(radius)
                covered += int(inside)
            per_node[node_id] = {
                "aligned_position_m": [aligned[0], aligned[1]],
                "truth_position_m": [truth[node_id][0], truth[node_id][1]],
                "error_m": error,
                "reported_error_radius_95_m": radius,
                "inside_reported_95_region": inside,
            }
        result["node_errors"] = per_node
        result["node_uncertainty_95_coverage_fraction"] = (covered / eligible) if eligible else None
        result["node_uncertainty_95_eligible_count"] = eligible

        person = gt.get("person_position_m")
        if isinstance(target, dict) and isinstance(person, list) and len(person) >= 2 and target.get("x_m") is not None and target.get("y_m") is not None:
            aligned_target = f((float(target["x_m"]), float(target["y_m"])))
            error = dist(aligned_target, (float(person[0]), float(person[1])))
            radius = target.get("error_radius_95_m")
            result["target_aligned_position_m"] = [aligned_target[0], aligned_target[1]]
            result["target_error_m"] = error
            result["target_reported_error_radius_95_m"] = radius
            result["target_inside_reported_95_region"] = bool(radius is not None and error <= float(radius))

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    gt = load_json(args.ground_truth)
    if not isinstance(gt, dict):
        raise SystemExit("Invalid ground-truth JSON")
    result = validate(args.directory, gt)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
