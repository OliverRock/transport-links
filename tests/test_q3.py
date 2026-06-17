"""Q3 behavioural checks. Run: python3 tests/test_q3.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from petrochem import (build_edges, build_solver_input, diff_runs,
                       infer_transport_edges, load, stub_solve, with_shock)

DATA = Path(__file__).resolve().parent.parent / "take_home_data"


def _setup():
    facilities, units, links = load(DATA)
    edges = build_edges(facilities, units, links) + infer_transport_edges(facilities, units)
    si = build_solver_input(units, edges)
    name = {f.id: f.name for f in facilities}
    unit_fac = {u.id: u.facility_id for u in units}
    return facilities, units, si, (lambda uid: name[unit_fac[uid]])


def test_baseline_supplies_every_cracker():
    *_, si, _ = _setup()
    _, fulfilment = stub_solve(si)
    assert all(v > 0 for v in fulfilment.values()) and len(fulfilment) == 5


def test_barge_closure_starves_all_but_the_pipeline_fed_cracker():
    _, _, si, name = _setup()
    base = stub_solve(si)
    shock = stub_solve(with_shock(si, blocked_modes={"barge"}))
    lost, _ = diff_runs(base, shock)
    # Moerdijk is the only cracker fed by observed pipelines (not barges) -> survives
    survivors = [name(s) for s, v in shock[1].items() if v > 0]
    assert survivors == ["Moerdijk Chemicals (Shell)"]
    assert len(lost) == 4


def test_facility_offline_is_localized():
    facilities, _, si, name = _setup()
    antwerp = next(f.id for f in facilities if f.name == "Antwerp [BE]")
    base = stub_solve(si)
    shock = stub_solve(with_shock(si, offline_facilities={antwerp}))
    lost = {name(s) for s in diff_runs(base, shock)[0]}
    assert "Chemelot-Geleen Chemical Complex" in lost      # its barge sourced from Antwerp
    assert "Antwerp Petrochemicals (BASF)" in lost
    assert "Moerdijk Chemicals (Shell)" not in lost         # fed elsewhere -> unaffected


def test_shock_is_non_destructive():
    *_, si, _ = _setup()
    before = dict(si.node_capacity)
    with_shock(si, offline_facilities=set(si.facility_of.values()), blocked_modes={"barge", "sea"})
    assert si.node_capacity == before  # overlay returned a new input; original untouched


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
