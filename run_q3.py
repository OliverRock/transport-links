"""Q3 demo: what-if scenario analysis.

baseline = solve(input);  shock = solve(overlay(input));  diff(baseline, shock)
The shock is a capacity overlay on the solver input (a facility forced to 0, or a whole
mode blocked) — raw data and graph topology are untouched. The solver is a reachability
stub standing in for the real most-likely-flow black box.

    python3 run_q3.py
"""
from pathlib import Path

from petrochem import (build_edges, build_solver_input, diff_runs,
                       infer_transport_edges, load, stub_solve, with_shock)

DATA = Path(__file__).parent / "take_home_data"


def main() -> None:
    facilities, units, links = load(DATA)
    fac_name = {f.id: f.name for f in facilities}
    unit_fac = {u.id: u.facility_id for u in units}

    edges = build_edges(facilities, units, links) + infer_transport_edges(facilities, units)
    si = build_solver_input(units, edges)

    def cracker(uid):
        return fac_name[unit_fac[uid]]

    baseline = stub_solve(si)
    supplied = [cracker(s) for s, v in baseline[1].items() if v > 0]
    print(f"BASELINE — crackers supplied: {len(supplied)}/{len(baseline[1])}")
    for n in supplied:
        print(f"    + {n}")

    antwerp = next(f.id for f in facilities if f.name == "Antwerp [BE]")
    scenarios = [
        ("Antwerp port offline", dict(offline_facilities={antwerp})),
        ("Rhine barge closure (block all barges)", dict(blocked_modes={"barge"})),
    ]
    for label, kwargs in scenarios:
        shock = stub_solve(with_shock(si, **kwargs))
        lost, dark = diff_runs(baseline, shock)
        print(f"\nSHOCK — {label}")
        print(f"    crackers starved: {len(lost)}   edges gone dark: {dark}")
        for uid in lost:
            print(f"    - {cracker(uid)}")
        if not lost:
            print("    (network is resilient — all crackers still supplied)")

    # data/topology untouched by the shocks
    assert all(c == float("inf") for c in si.node_capacity.values())
    print("\n(baseline input unchanged — shocks were non-destructive overlays)")


if __name__ == "__main__":
    main()
