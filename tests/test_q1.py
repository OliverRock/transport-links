"""Behavioural checks. Run: python3 tests/test_q1.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from petrochem import (Facility, Link, Unit, build_edges, facility_roles,
                       load, trace_upstream)

DATA = Path(__file__).resolve().parent.parent / "take_home_data"


def test_roles():
    assert facility_roles(["crude_distillation"]) == {"refinery"}
    assert facility_roles(["steam_cracker"]) == {"cracker"}
    # a facility can be several things at once — a single-label model couldn't express these
    assert facility_roles(["crude_distillation", "steam_cracker"]) == {"refinery", "cracker"}
    assert facility_roles(["oil_field_extraction", "crude_distillation"]) == {"oil_field", "refinery"}
    assert facility_roles(["crude_distillation", "port_import"]) == {"refinery", "port"}


def test_corridor_connects_facilities_along_route():
    facilities, units, links = load(DATA)
    by_id = {u.id: u for u in units}
    edges = build_edges(facilities, units, links)

    # naphtha corridor: refineries ON the route are the real sources feeding the cracker,
    # not the port the old endpoint-only snap used.
    naphtha = [e for e in edges if e.commodity == "naphtha" and e.resolved]
    assert any(by_id[e.from_unit].unit_type == "crude_distillation"
               and by_id[e.to_unit].unit_type == "steam_cracker" for e in naphtha)

    # crude corridor: no oil field in scope, so a port stands in as the source (and is
    # flagged with a lower confidence via the port-fill penalty).
    crude = [e for e in edges if e.commodity == "crude" and e.resolved]
    assert crude and all(by_id[e.to_unit].unit_type == "crude_distillation" for e in crude)
    assert any("inferred via port" in e.note for e in crude)

    # ethylene: produced by a cracker on the route, but no in-scope consumer -> dangling.
    ethylene = [e for e in edges if e.commodity == "ethylene"]
    assert ethylene and all(by_id[e.from_unit].unit_type == "steam_cracker"
                            and e.to_unit is None for e in ethylene)


def test_trace_stops_at_data_boundary():
    facilities, units, links = load(DATA)
    by_id = {u.id: u for u in units}
    edges = build_edges(facilities, units, links)
    cracker = next(u for u in units if u.name == "Ethylene")  # Moerdijk
    steps, boundary, unmet = trace_upstream(by_id, edges, cracker.id)
    assert any(e.commodity == "naphtha" for _, e in steps)
    assert not boundary  # no oil field in this slice
    assert any("Rotterdam" in by_id[u].name for u, _ in unmet)


def test_oil_field_slots_in_for_free():
    """Adding a source + crude link extends the trace to the field with no code changes."""
    facilities, units, links = load(DATA)
    pernis = next(f for f in facilities if f.name == "Shell Pernis Refinery")
    field = Facility("field01", "Test Oil Field", pernis.lat + 0.01, pernis.lon + 0.01)
    field_unit = Unit("u_field", "field01", "Extractor", "oil_field_extraction")
    crude_link = Link("crude", "pipeline",
                      [[[field.lon, field.lat], [pernis.lon, pernis.lat]]])

    units2 = units + [field_unit]
    by_id = {u.id: u for u in units2}
    edges = build_edges(facilities + [field], units2, links + [crude_link])
    cdu = next(u for u in units if u.unit_type == "crude_distillation" and u.facility_id == pernis.id)
    steps, boundary, _ = trace_upstream(by_id, edges, cdu.id)
    assert any(e.commodity == "crude" for _, e in steps)
    assert field_unit.id in boundary


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
