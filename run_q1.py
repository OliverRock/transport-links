"""Q1 demo: build the unit-level graph from the sample and trace upstream from a cracker.

    python3 run_q1.py
"""
from pathlib import Path

from petrochem import build_edges, facility_roles, load, trace_upstream

DATA = Path(__file__).parent / "take_home_data"


def main() -> None:
    facilities, units, links = load(DATA)
    edges = build_edges(facilities, units, links)
    units_by_id = {u.id: u for u in units}
    fac_name = {f.id: f.name for f in facilities}
    units_by_fac = {}
    for u in units:
        units_by_fac.setdefault(u.facility_id, []).append(u)

    def site(unit_id):  # facility name for a unit (units are generically named, e.g. "CDU")
        return fac_name[units_by_id[unit_id].facility_id] if unit_id else "UNRESOLVED"

    print("FACILITY ROLES (inferred from contained units)")
    for f in facilities:
        types = [u.unit_type for u in units_by_fac.get(f.id, [])]
        roles = "+".join(sorted(facility_roles(types))) or "unknown"
        print(f"  {f.name:38s} {roles}")

    print("\nRESOLVED EDGES (one pipeline corridor -> many producer->consumer edges)")
    for e in edges:
        print(f"  {e.commodity:9s} {site(e.from_unit):28s} -> {site(e.to_unit):28s}"
              f"  (conf {e.confidence}, {e.note})")

    print("\nUPSTREAM TRACE from each cracker")
    for c in (u for u in units if u.unit_type == "steam_cracker"):
        steps, boundary, unmet = trace_upstream(units_by_id, edges, c.id)
        print(f"  {fac_name[c.facility_id]}")
        for depth, e in sorted(steps, key=lambda s: s[0]):
            print(f"    {'  ' * depth}<-{e.commodity} from {site(e.from_unit)} (conf {e.confidence})")
        if boundary:
            print(f"    reached source(s): {', '.join(site(b) for b in boundary)}")
        if not steps:
            print("    (no inbound material in this slice)")
        elif unmet:
            print(f"    stops at data boundary: {site(unmet[0][0])} needs {unmet[0][1]}")


if __name__ == "__main__":
    main()
