"""Petrochemical connectivity model (Q1) — minimal demo, stdlib only.

The chain is a unit-level flow graph: units are nodes, each with a recipe saying what
commodity it consumes and produces; transport links are edges. The transport data has
geometries but NO endpoints, so edges are *constructed* by snapping each geometry end to
the nearest recipe-compatible facility (and flagged with a confidence). Tracing is a
reverse walk that follows a commodity upstream until it hits a source or the data edge.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --- domain: unit recipes (commodity inputs -> outputs), kept as data -------------------
# Adding a unit type is a new row here; no other code changes. "*" = pass-through (ports).
WILDCARD = "*"
RECIPES: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "oil_field_extraction": ((),            ("crude",)),
    "crude_distillation":   (("crude",),    ("naphtha", "diesel")),
    "steam_cracker":        (("naphtha",),  ("ethylene", "olefins")),
    "port_import":          ((WILDCARD,),   (WILDCARD,)),
    "port_export":          ((WILDCARD,),   (WILDCARD,)),
}


def produces(unit_type: str, c: str) -> bool:
    outs = RECIPES[unit_type][1]
    return c in outs or WILDCARD in outs


def consumes(unit_type: str, c: str) -> bool:
    ins = RECIPES[unit_type][0]
    return c in ins or WILDCARD in ins


def upstream_commodities(unit_type: str, produced: str) -> List[str]:
    """What a unit had to consume to produce `produced`. Ports pass the commodity
    through unchanged; a refinery that produced naphtha consumed crude."""
    ins = RECIPES[unit_type][0]
    return [produced] if WILDCARD in ins else list(ins)


# A unit's base role. A facility's role is just the SET of these over its units —
# never a single label, because a site can be several things at once (a refinery with
# its own port terminal, an oil field with on-site distillation, a refinery+cracker
# "integrated complex"). Role is a derived view for humans; the flow model uses units.
ROLE_OF_UNIT = {
    "oil_field_extraction": "oil_field",
    "crude_distillation": "refinery",
    "steam_cracker": "cracker",
    "port_import": "port",
    "port_export": "port",
}


def facility_roles(unit_types) -> set:
    return {ROLE_OF_UNIT[t] for t in unit_types if t in ROLE_OF_UNIT}


# --- entities ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Facility:
    id: str
    name: str
    lat: float
    lon: float

    @property
    def point(self) -> Tuple[float, float]:
        return (self.lon, self.lat)  # GeoJSON order


@dataclass(frozen=True)
class Unit:
    id: str
    facility_id: str
    name: str
    unit_type: str


@dataclass(frozen=True)
class Link:  # raw transport record: a geometry + commodity, with NO endpoints
    commodity: str
    mode: str
    geometry: list  # MultiLineString


@dataclass(frozen=True)
class Edge:  # a resolved, directed, commodity-typed connection between units
    commodity: str
    mode: str
    from_unit: Optional[str]
    to_unit: Optional[str]
    confidence: float
    note: str

    @property
    def resolved(self) -> bool:
        return self.from_unit is not None and self.to_unit is not None


# --- loading ----------------------------------------------------------------------------

def load(data_dir: Path) -> Tuple[List[Facility], List[Unit], List[Link]]:
    with open(data_dir / "facilities.csv", newline="") as f:
        facilities = [Facility(r["id"], r["name"], float(r["lat"]), float(r["lon"]))
                      for r in csv.DictReader(f)]
    with open(data_dir / "units.csv", newline="") as f:
        units = [Unit(r["id"], r["facility_id"], r["name"], r["unit_type"])
                 for r in csv.DictReader(f)]
    with open(data_dir / "pipelines.geojson") as f:
        links = [Link(ft["properties"]["commodity"], ft["properties"]["mode"],
                      ft["geometry"]["coordinates"])
                 for ft in json.load(f)["features"]]
    return facilities, units, links


# --- building edges from edgeless geometries --------------------------------------------

# A pipeline is a shared *corridor*, not a point-to-point link: facilities inject and tap
# along its whole length, so we resolve against every vertex, not just the drawn ends.
BUFFER_KM = 5.0    # a facility within this of the route is treated as on the corridor
CONF_SCALE = 10.0  # confidence = 1 - route_distance / CONF_SCALE
PORT_FILL = 0.5    # certainty penalty when a wildcard port stands in for a missing side


def haversine_km(a, b) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    p = math.pi / 180
    h = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def _on_route(verts, commodity, facilities, units_by_fac):
    """Facilities within BUFFER_KM of ANY vertex that have a recipe-compatible unit.
    Returns [(facility, min_route_distance_km, units_at_facility)]."""
    hits = []
    for f in facilities:
        dmin = min(haversine_km(f.point, (v[0], v[1])) for v in verts)
        if dmin > BUFFER_KM:
            continue
        us = units_by_fac.get(f.id, [])
        if any(produces(u.unit_type, commodity) or consumes(u.unit_type, commodity) for u in us):
            hits.append((f, dmin, us))
    return hits


def _exact(hits, commodity, side):
    """Hits that *really* produce/consume the commodity (exact recipe match, not wildcard)."""
    idx = 1 if side == "producer" else 0  # RECIPES = (inputs, outputs)
    return [(f, d, us) for (f, d, us) in hits
            if any(commodity in RECIPES[u.unit_type][idx] for u in us)]


def _is_port(units) -> bool:
    return bool(units) and all(u.unit_type.startswith("port_") for u in units)


def _pick_unit(units, commodity, want) -> str:
    idx = 1 if want == "producer" else 0
    real = [u for u in units if commodity in RECIPES[u.unit_type][idx]]
    port_pref = "port_import" if want == "producer" else "port_export"
    ports = [u for u in units if u.unit_type == port_pref]
    compatible = [u for u in units
                  if (produces if want == "producer" else consumes)(u.unit_type, commodity)]
    return (real or ports or compatible)[0].id


def _resolve(link: Link, facilities, units_by_fac) -> List[Edge]:
    c = link.commodity
    verts = [pt for seg in link.geometry for pt in seg]
    hits = _on_route(verts, c, facilities, units_by_fac)

    producers = _exact(hits, c, "producer")
    consumers = _exact(hits, c, "consumer")
    ports = [h for h in hits if _is_port(h[2])]
    src_filled = dst_filled = False
    if not producers:           # no real source on the corridor -> a port imported it
        producers, src_filled = ports, True
    if not consumers:           # no real sink -> a port will export it
        consumers, dst_filled = ports, True

    edges: List[Edge] = []
    # Dangling: material made (or needed) here but no counterpart in scope — kept, flagged.
    if producers and not consumers:
        return [Edge(c, link.mode, _pick_unit(pu, c, "producer"), None, 0.0,
                     f"on-route src={round(pd, 1)}km; no in-scope consumer")
                for (pf, pd, pu) in producers]
    if consumers and not producers:
        return [Edge(c, link.mode, None, _pick_unit(cu, c, "consumer"), 0.0,
                     f"on-route dst={round(cd, 1)}km; no in-scope producer")
                for (cf, cd, cu) in consumers]
    if src_filled and dst_filled:
        return []  # only ports on the corridor: nothing real to assert

    factor = (PORT_FILL if src_filled else 1.0) * (PORT_FILL if dst_filled else 1.0)
    for (pf, pd, pu) in producers:
        for (cf, cd, cu) in consumers:
            if pf.id == cf.id:
                continue
            conf = round(max(0.0, 1 - max(pd, cd) / CONF_SCALE) * factor, 2)
            note = f"on-route src/dst = {round(pd, 1)}km/{round(cd, 1)}km"
            if src_filled:
                note += "; source inferred via port"
            if dst_filled:
                note += "; sink inferred via port"
            edges.append(Edge(c, link.mode, _pick_unit(pu, c, "producer"),
                              _pick_unit(cu, c, "consumer"), conf, note))
    return edges


def build_edges(facilities, units, links) -> List[Edge]:
    units_by_fac: Dict[str, List[Unit]] = {}
    for u in units:
        units_by_fac.setdefault(u.facility_id, []).append(u)
    return [e for l in links for e in _resolve(l, facilities, units_by_fac)]


# --- Q2: inferring the invisible transport (sea lanes & barges) -------------------------
# We have no barge data and no sea-lane data, so we *invent* plausible edges from cheap
# priors (distance) gated by hard mode-feasibility, and mark them with a low confidence.
# Ethylene is a gas -> excluded from both modes (dedicated pipeline only). No river/coast
# geometry: barge "navigability" is approximated by a distance cap (the honest weak spot).
SEA_MAX_KM, BARGE_MAX_KM = 2000.0, 300.0
SEA_FACTOR, BARGE_FACTOR = 0.5, 0.4  # inferred-trust tiers; barge lowest (no river data)


def _inferred_conf(dist, max_km, factor) -> float:
    return round(max(0.0, 1 - dist / max_km) * factor, 2)


def infer_transport_edges(facilities, units) -> List[Edge]:
    units_by_fac: Dict[str, List[Unit]] = {}
    for u in units:
        units_by_fac.setdefault(u.facility_id, []).append(u)

    def roles(f):
        return facility_roles(u.unit_type for u in units_by_fac.get(f.id, []))

    ports = [f for f in facilities if "port" in roles(f)]
    crackers = [f for f in facilities if "cracker" in roles(f)]
    refineries = [f for f in facilities if "refinery" in roles(f)]

    def edge(a, b, commodity, mode, conf, kind):
        d = haversine_km(a.point, b.point)
        return Edge(commodity, mode,
                    _pick_unit(units_by_fac[a.id], commodity, "producer"),
                    _pick_unit(units_by_fac[b.id], commodity, "consumer"),
                    conf, f"inferred {kind}, {round(d)}km")

    edges: List[Edge] = []
    # Sea lanes: ports are mutually sea-connected (one edge per pair).
    for i, a in enumerate(ports):
        for b in ports[i + 1:]:
            d = haversine_km(a.point, b.point)
            if d <= SEA_MAX_KM:
                edges.append(edge(a, b, "naphtha", "sea",
                                  _inferred_conf(d, SEA_MAX_KM, SEA_FACTOR), "sea lane"))
    # Barges: feed each inland consumer from its nearest port (naphtha->cracker, crude->refinery).
    def nearest_port(f):
        return min(ports, key=lambda p: haversine_km(p.point, f.point)) if ports else None

    for sinks, commodity in [(crackers, "naphtha"), (refineries, "crude")]:
        for f in sinks:
            p = nearest_port(f)
            if p is None:
                continue
            d = haversine_km(p.point, f.point)
            if d <= BARGE_MAX_KM:
                edges.append(edge(p, f, commodity, "barge",
                                  _inferred_conf(d, BARGE_MAX_KM, BARGE_FACTOR), "barge"))
    return edges


# --- tracing ----------------------------------------------------------------------------

def trace_upstream(units_by_id, edges, target_id):
    """Reverse walk from a unit, following each input commodity through producing units.
    Returns (steps, boundary, unmet): steps are (depth, Edge); boundary are true sources
    reached (e.g. oil fields); unmet are (unit, commodity) needs with no upstream link."""
    target = units_by_id[target_id]
    frontier = [(target_id, c, 0) for c in RECIPES[target.unit_type][0] if c != WILDCARD]
    seen, steps, boundary, unmet = set(), [], set(), []

    while frontier:
        uid, commodity, depth = frontier.pop()
        if (uid, commodity) in seen:
            continue
        seen.add((uid, commodity))
        inbound = [e for e in edges if e.resolved and e.to_unit == uid and e.commodity == commodity]
        if not inbound:
            unmet.append((uid, commodity))
            continue
        for e in inbound:
            steps.append((depth, e))
            src_type = units_by_id[e.from_unit].unit_type
            needed = [c for c in upstream_commodities(src_type, commodity) if c != WILDCARD]
            if not needed:
                boundary.add(e.from_unit)  # a true source: nothing further upstream
            for c in needed:
                frontier.append((e.from_unit, c, depth + 1))
    return steps, boundary, unmet


# --- Q3: scenario analysis ("what-if") --------------------------------------------------
# We DON'T own the solver — we own its interface. Contract:
#   in:  nodes (unit -> capacity), edges (-> capacity), implicit sources/sinks from recipes
#   out: per-edge flow, and per-sink fulfilment (fraction of demand met)
# A shock is a *capacity overlay* on that input (set capacity to 0 / a fraction), NOT a
# graph edit and NOT a data edit: raw data stays immutable, the solver stays a pure black
# box, and baseline vs shock keep an identical topology so the diff is element-by-element.
# Transport is uncapacitated (capacity = INF); the capacity field is only the shock lever.
INF = float("inf")
IMPORTABLE = {"crude", "naphtha"}  # what an import port can bring in from outside the region


@dataclass(frozen=True)
class FlowEdge:
    from_unit: str
    to_unit: str
    commodity: str
    mode: str
    capacity: float = INF


@dataclass
class SolverInput:
    node_capacity: Dict[str, float]   # unit_id -> capacity (INF unless shocked)
    edges: List[FlowEdge]
    unit_type: Dict[str, str]
    facility_of: Dict[str, str]


def build_solver_input(units, edges) -> SolverInput:
    return SolverInput(
        node_capacity={u.id: INF for u in units},
        edges=[FlowEdge(e.from_unit, e.to_unit, e.commodity, e.mode) for e in edges if e.resolved],
        unit_type={u.id: u.unit_type for u in units},
        facility_of={u.id: u.facility_id for u in units},
    )


def stub_solve(si: SolverInput):
    """Placeholder for the real most-likely-flow solver. Reachability only (uncapacitated):
    propagate, from import ports / oil fields, which commodity each node can supply through
    live edges. Returns (edge_flows aligned to si.edges, fulfilment {sink_unit: 0|1})."""
    cap = si.node_capacity
    def live(e):
        return e.capacity > 0 and cap[e.from_unit] > 0 and cap[e.to_unit] > 0

    supplies = {n: set() for n in si.node_capacity}
    received = {n: set() for n in si.node_capacity}
    for n, ut in si.unit_type.items():
        if cap[n] <= 0:
            continue
        if ut == "port_import":
            supplies[n] |= IMPORTABLE
        elif ut == "oil_field_extraction":
            supplies[n] |= {"crude"}

    changed = True
    while changed:  # fixpoint: deliver along live edges, then let converters/ports re-emit
        changed = False
        for e in si.edges:
            if live(e) and e.commodity in supplies[e.from_unit] and e.commodity not in received[e.to_unit]:
                received[e.to_unit].add(e.commodity); changed = True
        for n, ut in si.unit_type.items():
            if cap[n] <= 0:
                continue
            ins, outs = RECIPES[ut]
            if WILDCARD in ins:                      # connector (port): passes through
                add = received[n] - supplies[n]
            elif ins and all(c in received[n] for c in ins):  # converter: has all inputs
                add = set(outs) - supplies[n]
            else:
                add = set()
            if add:
                supplies[n] |= add; changed = True

    edge_flows = [1.0 if (live(e) and e.commodity in supplies[e.from_unit]) else 0.0
                  for e in si.edges]
    fulfilment = {n: (1.0 if (cap[n] > 0 and "naphtha" in received[n]) else 0.0)
                  for n, ut in si.unit_type.items() if ut == "steam_cracker"}
    return edge_flows, fulfilment


def with_shock(si: SolverInput, offline_facilities=(), blocked_modes=()) -> SolverInput:
    """Apply a what-if as a capacity overlay; returns a NEW input, leaving `si` untouched."""
    off = set(offline_facilities)
    blocked = set(blocked_modes)
    return SolverInput(
        node_capacity={n: (0.0 if si.facility_of[n] in off else c)
                       for n, c in si.node_capacity.items()},
        edges=[FlowEdge(e.from_unit, e.to_unit, e.commodity, e.mode,
                        0.0 if e.mode in blocked else e.capacity) for e in si.edges],
        unit_type=si.unit_type,
        facility_of=si.facility_of,
    )


def diff_runs(baseline, shock):
    """What changed between two solver runs: sinks that lost supply, edges that went dark."""
    base_flows, base_ful = baseline
    shock_flows, shock_ful = shock
    lost_sinks = [s for s in base_ful if base_ful[s] > 0 and shock_ful[s] == 0]
    dark_edges = sum(1 for b, s in zip(base_flows, shock_flows) if b > 0 and s == 0)
    return lost_sinks, dark_edges
