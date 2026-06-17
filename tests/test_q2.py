"""Q2 behavioural checks. Run: python3 tests/test_q2.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from petrochem import infer_transport_edges, load

DATA = Path(__file__).resolve().parent.parent / "take_home_data"


def test_no_ethylene_by_barge_or_sea():
    # ethylene is a gas -> dedicated pipeline only; never inferred as barge/sea
    _, units, _ = load(DATA)
    inferred = infer_transport_edges(load(DATA)[0], units)
    assert all(e.commodity != "ethylene" for e in inferred)
    assert all(e.mode in ("sea", "barge") for e in inferred)


def test_inference_connects_every_cracker():
    facilities, units, _ = load(DATA)
    inferred = infer_transport_edges(facilities, units)
    cracker_ids = {u.id for u in units if u.unit_type == "steam_cracker"}
    reached = {e.to_unit for e in inferred}
    assert cracker_ids <= reached  # the isolated crackers now have an inferred inbound edge


def test_inferred_confidence_is_low_and_barges_lowest():
    facilities, units, _ = load(DATA)
    inferred = infer_transport_edges(facilities, units)
    assert all(e.confidence <= 0.5 for e in inferred)  # inferred, not measured
    barge = [e.confidence for e in inferred if e.mode == "barge"]
    sea = [e.confidence for e in inferred if e.mode == "sea"]
    assert max(barge) <= max(sea)  # barge is the lowest-trust tier (no river data)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
