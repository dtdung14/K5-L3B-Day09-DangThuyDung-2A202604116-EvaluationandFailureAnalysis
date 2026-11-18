"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    problems += _report_problems(pr, base, spec)
    if base_spec is not None:
        problems += ratchet_problems(spec, base_spec)
    return problems


SAFETY_SUMS = ("secret_leak", "approval_bypass")   # aggregated as counts in lab9.eval.aggregate


def _is_bad_number(v) -> bool:
    return isinstance(v, float) and not math.isfinite(v)


def _graded_ids(spec: dict, base: dict) -> list[str]:
    """Spec metrics that are scored per row: the ones the baseline's rows carry a value for."""
    base_keys = set().union(*(r.keys() for r in base.get("rows") or [{}]))
    return [m["id"] for m in spec.get("metrics") or [] if m["id"] in base_keys]


def _report_problems(pr: dict, base: dict, spec: dict) -> list[str]:
    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}

    # 1. metric values: NaN / inf never compare as "below the floor", so they must never reach it.
    for k, v in (pr.get("metrics") or {}).items():
        if _is_bad_number(v):
            problems.append(f"metric {k} is {v} (NaN/inf hides a failure from the threshold)")
    for m in spec.get("metrics") or []:
        if m["id"] not in (pr.get("metrics") or {}):
            problems.append(f"metric {m['id']} in the spec is absent from the report")

    # 2. graders: a crash is not a pass.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the report "
                        f"(first: {str(pr['evaluator_failures'][0])[:80]})")
    graded = _graded_ids(spec, base)
    for r in rows:
        for m in graded:
            v = r.get(m)
            if v is None or _is_bad_number(v) or not isinstance(v, (bool, int)):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')}: {m} is {v!r} (crashed/missing grade)")
                break

    # 3. coverage: every (item, seed) exactly once, the same set as the baseline.
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"{len(dups)} duplicated (item, seed) row(s), e.g. {dups[0]}")
    want_n = int(bm.get("items") or 0) * len(bm.get("seeds") or [])
    if want_n and len(rows) != want_n:
        problems.append(f"{len(rows)} rows, baseline manifest says {bm.get('items')} items x "
                        f"{len(bm.get('seeds') or [])} seeds = {want_n} (dropped/duplicated rows)")
    own_n = int(pm.get("items") or 0) * len(pm.get("seeds") or [])
    if len(rows) != own_n:
        problems.append(f"{len(rows)} rows but the report's own manifest promises {own_n}")
    for field in ("items", "seeds", "eval_set", "metric_spec_version"):
        if field in bm and pm.get(field) != bm.get(field):
            problems.append(f"manifest {field} {pm.get(field)!r} != baseline {bm.get(field)!r}")
    if spec.get("seeds") and list(pm.get("seeds") or []) != list(spec["seeds"]):
        problems.append(f"report seeds {pm.get('seeds')} != spec seeds {spec['seeds']} (cherry-picked seeds)")
    pr_set, base_set = set(keys), {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if pr_set != base_set:
        missing, extra = base_set - pr_set, pr_set - base_set
        problems.append(f"(item, seed) set differs from the baseline: {len(missing)} missing, {len(extra)} extra"
                        + (f", e.g. missing {sorted(missing, key=str)[0]}" if missing else ""))

    # 4. slice tags come from the labels: they may not move between baseline and PR.
    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    for r in rows:
        iid = r.get("item_id")
        if iid in base_slices and sorted(r.get("slices") or []) != base_slices[iid]:
            problems.append(f"item {iid} slice tags {sorted(r.get('slices') or [])} != baseline {base_slices[iid]}")
            break

    # 5. headline metrics must be what the rows say (a hand-edited number with untouched rows).
    if rows and not dups:
        for m, want in _recompute(rows, graded, spec).items():
            got = (pr.get("metrics") or {}).get(m)
            if isinstance(got, (int, float)) and not _is_bad_number(got) and want is not None \
                    and abs(float(got) - float(want)) > 1e-3:
                problems.append(f"metric {m}={got} but its rows give {want} (report edited after the run)")
    return problems


def _recompute(rows: list[dict], graded: list[str], spec: dict) -> dict:
    """Same arithmetic as lab9.eval.aggregate, limited to what rows determine (no cost)."""
    out: dict = {}
    for m in graded:
        vals = [r[m] for r in rows if isinstance(r.get(m), (bool, int))]
        if not vals:
            continue
        out[m] = sum(vals) if m in SAFETY_SUMS else round(sum(vals) / len(vals), 4)
    if "pass_rate" in graded:
        by_item: dict = {}
        for r in rows:
            by_item.setdefault(r.get("item_id"), []).append(bool(r.get("pass_rate")))
        out["pass_5"] = round(sum(all(v) for v in by_item.values()) / len(by_item), 4)
        for k in spec.get("pass_k") or []:
            if min(len(v) for v in by_item.values()) < k:
                continue
            for name, fn in (("pass_at", stats.pass_at_k), ("pass_hat", stats.pass_hat_k)):
                est = [fn(len(v), sum(v), k) for v in by_item.values()]
                out[f"{name}_{k}"] = round(sum(est) / len(est), 4)
    return out


def ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version => thresholds may only get stricter. A new eval-set version starts over."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    problems: list[str] = []
    for field in ("eval_set", "labels", "adversarial_pack"):
        if base_spec.get(field) != spec.get(field):
            problems.append(f"RATCHET {field} changed ({base_spec.get(field)!r} -> {spec.get(field)!r}) on the same version")
    if list(spec.get("seeds") or []) != list(base_spec.get("seeds") or []):
        problems.append(f"RATCHET seeds changed {base_spec.get('seeds')} -> {spec.get('seeds')}")
    if not set(base_spec.get("pass_k") or []) <= set(spec.get("pass_k") or []):
        problems.append(f"RATCHET pass_k dropped {sorted(set(base_spec.get('pass_k') or []) - set(spec.get('pass_k') or []))}")
    bb, sb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if bb.get("rng") != sb.get("rng") or bb.get("method") != sb.get("method"):
        problems.append("RATCHET bootstrap rng/method changed (re-rolling the CI until it passes)")
    if (sb.get("confidence") or 0.95) > (bb.get("confidence") or 0.95):
        problems.append("RATCHET bootstrap confidence raised (a wider CI blocks less)")
    if (sb.get("n_resamples") or 1000) < (bb.get("n_resamples") or 1000):
        problems.append("RATCHET bootstrap n_resamples lowered")

    new = {m["id"]: m for m in spec.get("metrics") or []}
    for old in base_spec.get("metrics") or []:
        mid = old["id"]
        if mid not in new:
            problems.append(f"RATCHET metric {mid} removed")
            continue
        problems += [f"RATCHET metric {mid}: {p}" for p in _looser(old, new[mid])]

    new_sl = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for old in base_spec.get("slices") or []:
        key = (old["name"], old["metric"])
        if key not in new_sl:
            problems.append(f"RATCHET slice {key[0]}/{key[1]} removed")
            continue
        problems += [f"RATCHET slice {key[0]}/{key[1]}: {p}" for p in _looser(old, new_sl[key], slice_=True)]
    return problems


def _looser(old: dict, new: dict, slice_: bool = False) -> list[str]:
    out = []
    ot = old if slice_ else (old.get("threshold") or {})
    nt = new if slice_ else (new.get("threshold") or {})
    default_blocking = True if slice_ else False
    if old.get("blocking", default_blocking) and not new.get("blocking", default_blocking):
        out.append("blocking -> non-blocking")
    if "min" in ot and ("min" not in nt or nt["min"] < ot["min"]):
        out.append(f"min {ot['min']} -> {nt.get('min')}")
    if "max" in ot and ("max" not in nt or nt["max"] > ot["max"]):
        out.append(f"max {ot['max']} -> {nt.get('max')}")
    if "max_increase" in ot and ("max_increase" not in nt or nt["max_increase"] > ot["max_increase"]):
        out.append(f"max_increase {ot['max_increase']} -> {nt.get('max_increase')}")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    if not slice_ and old.get("kind") != new.get("kind"):
        out.append(f"kind {old.get('kind')} -> {new.get('kind')}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note = "ok", ""
        if not a:
            # A slice gate with no rows proves nothing: treat as missing, never as a pass.
            verdict, value = "missing", None
        else:
            value = round(sum(a.values()) / len(a), 4)
            if "min" in sl and value < sl["min"]:
                verdict = "fail"
            if "max" in sl and value > sl["max"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking", True):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking", True) else "warn")
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<44} {value!s:<8} n={len(a):<3} {json.dumps(th):<44} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
