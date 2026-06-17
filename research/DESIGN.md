# Design — Q1: Domain Model

*How we model the petrochemical network so we can trace material flow upstream, given
units-as-nodes and conversion-recipes-as-data.*

## 1. The shape of the model in one picture

A petrochemical chain is a **metabolic network**: units are reactions, commodities are
metabolites, conversion happens *inside* a unit. So the flow graph is over **units**, and
the commodity identity only ever changes *at a unit*. Facilities are a compartment layer
that groups units and is where transport physically attaches.

```
  [oil_field]      crude        crude          naphtha          ethylene
   (source)   ──────────▶  [crude_distillation] ──────▶ [steam_cracker] ──────▶ ...
   ∅→crude     transport      crude→{naphtha,    transport   naphtha→{ethylene,
                              diesel} (refinery)            olefins} (cracker)
                                                  
                              └── facility = compartment grouping units ──┘
```

The thing that flows is a **commodity**. A **unit is the converter** — its recipe says
what it consumes and produces, so we don't need separate "conversion edges": the unit node
*is* the place a commodity turns into another. Edges only ever carry one commodity, from a
unit that *produces* it to a unit that *consumes* it.

## 2. Entities, identity, relationships

### Given entities (from the files — high confidence, never mutated)

| Entity | Identified by | Fields (from data) | Notes |
|---|---|---|---|
| **Facility** | `id` (stable 8-hex) | name, country, lat, lon, status | Role is **derived**, not stored. A point geometry. |
| **Unit** | `id` (`u_001…`) | facility_id (FK), name, unit_type, design_capacity_t_per_year, status | The flow node. `unit_type` → recipe. |
| **TransportLink** *(raw)* | `id` (uuid) | mode, commodity, baseline_distance_km, derivation, segment_names, geometry (MultiLineString) | **No endpoints given.** A geometry, not a relationship. |

**Facility role is a derived *set* of tags, not a single label** — a site is whatever its
units make it, possibly several at once: `crude_distillation` → refinery, `steam_cracker`
→ cracker, `port_*` → port, `oil_field_extraction` → oil_field. So a refinery with its own
jetty is `{refinery, port}`, an oil field with on-site distillation is `{oil_field,
refinery}`, a refinery+cracker is the classic integrated complex `{refinery, cracker}`. We
compute it for display; we never store it, and the flow model reads units, not roles —
which is why a facility can be any mixture without anything breaking. (Sample: 5 ports, 6
refineries, 5 crackers, each a single role — but the set model handles mixtures too.)

### Controlled vocabularies (the domain semantics, as data)

**Commodities:** `crude, naphtha, diesel, ethylene, olefins` (extensible).

**Unit-type recipes** — the heart of the model, a table not code:

| unit_type | inputs | outputs | role |
|---|---|---|---|
| `oil_field_extraction` | ∅ | crude | source |
| `crude_distillation` | crude | naphtha, diesel | intermediate |
| `steam_cracker` | naphtha | ethylene, olefins | sink |
| `port_import` | * | * | connector (into region) |
| `port_export` | * | * | connector (out of region) |

Adding a unit type = adding a row. No code change. Ports are commodity-agnostic
pass-throughs (`*`), which is why a port can sit on a crude *or* naphtha *or* ethylene leg.

### Derived entities (the inference layer — carries confidence)

| Entity | Identified by | Fields | Notes |
|---|---|---|---|
| **Edge** *(resolved)* | `(from_unit, to_unit, commodity, mode)` | direction, derivation, confidence, distance_km, source_link_id(s) | Built by resolving a TransportLink's geometry to units. |

This three-tier split — **given → resolved → flow** — is deliberate. Given facts never
change; resolved topology is uncertain and revisable (this is the Q2 seam); flow is a
separate solver artifact (the Q3 seam). Keeping them apart is what keeps the model honest
under partial data and keeps the solver a pure function.

## 3. Building edges from edgeless geometries (the Q1↔Q2 seam)

The data gives a geometry + commodity but no endpoints, so edges are **constructed**, not
read. A pipeline is a **shared corridor, not a point-to-point link** — real systems
(`RAPL`, `CEPS`, `Gasunie`…) inject and tap at many sites along their length — so we
resolve against the *whole route*, not just the two drawn vertices. (An earlier
endpoint-only version missed three refineries sitting ~1 km off the naphtha route and was
fooled by a stray gap-artifact vertex 72 km from anything; see the corridor evidence below.)

```
resolve(link):
  on_route = facilities within BUFFER_KM of ANY vertex, with a recipe-compatible unit
  producers = on_route facilities whose unit really outputs the commodity
  consumers = on_route facilities whose unit really inputs it
  if no producers: producers = ports on route   # imported in (flagged, port-fill penalty)
  if no consumers: consumers = ports on route   # exported out
  emit edge producer → consumer for each pair    # one corridor -> many edges
  confidence = (1 - route_distance / CONF_SCALE) * port_fill_penalty
  dangling: producers but no consumer (or vice-versa) -> keep edge, mark UNRESOLVED end
```

The recipe constraint is what makes this robust: only facilities that actually produce or
consume the commodity become endpoints, and wildcard ports only stand in when a real
producer/consumer is absent (and are penalised in confidence). Grounded in the real sample:

- **naphtha** corridor → runs past Pernis, BP and Botlek refineries (~1–3 km) → three
  high-confidence edges `refinery ──naphtha──▶ Moerdijk cracker`. The endpoint-only version
  had connected only a *port* to the cracker and missed the actual sources.
- **crude** corridor → no oil field in scope, so import ports stand in as sources feeding
  the Pernis and Botlek CDUs on the route — kept but flagged (`conf ≈ 0.4`,
  "source inferred via port").
- **ethylene** corridor → produced by the Antwerp and Chemelot crackers on the route, but
  no in-scope consumer (ethylene's consumers are downstream of our four unit types) →
  edges kept with an **UNRESOLVED** sink rather than a fabricated one.

So the same mechanism that builds edges also surfaces exactly where the data is too thin to
trust — which is the honest answer to "how do they relate when the relationship isn't given."

## 4. Tracing upstream from a cracker (what Q1 asks us to demonstrate)

Reverse traversal over the directed unit graph, following commodity identity through each
unit's recipe:

```
trace_upstream(target_unit):
  frontier = [(target_unit, c) for c in recipe(target).inputs]   # cracker → needs naphtha
  prov = DAG()
  while frontier:
     unit, commodity = pop()
     for edge in in_edges(unit) where edge.commodity == commodity:    # who delivers it?
        src = edge.from_unit                                          # a producing unit
        prov.add(edge)                                                # record provenance
        for c_in in recipe(src).inputs:        # what did src consume to make `commodity`?
           frontier.push((src, c_in))          # e.g. refinery consumed crude → recurse
  return prov   # a DAG of edges, each with confidence; aggregate = trace confidence
```

It terminates at **source units** (`oil_field_extraction`, or a `port_import` where the
chain leaves the modelled region) — i.e. "as far upstream as the sample data allows." For
this sample a cracker traces: `steam_cracker ◀naphtha◀ refinery ◀crude◀ port_import`, and
stops at the import boundary because oil fields aren't materialised. The result is a
provenance DAG, and because every edge carries `confidence`/`derivation`, a trace can be
reported as "this much is observed, this much inferred."

## 5. Oil-field slot-in (the test that the layering is right)

The brief asks how oil-field sourcing slots in without materialising records. By
construction it's free: add `oil_field_extraction` source nodes (recipe `∅ → crude`)
upstream of the `port_import`/distillation units, connected by crude sea-lane/pipeline
edges. **Nothing structural changes** — it's just another source layer, and `trace_upstream`
already walks through it because it stops at "units with no upstream input," not at a
hard-coded refinery boundary. If adding the field layer required touching the trace logic,
the model would be wrong; it doesn't, so it isn't.

## 6. Technology

This is a **demo, not a product**: one stdlib-only file, no dependencies, no build step.
Units are dataclass nodes; edges are a plain list filtered on traversal — fine at this
scale (16 facilities / 21 units). The graph is small enough that `networkx` would add a
dependency without earning it. Recipes are a dict, kept as data. The production direction
(property graph / relational + materialised views, typed loaders, persisted confidence)
is noted but deliberately not built.

## 7. Implementation & results

```
petrochem.py        the model: recipes, entities, load, edge-resolution, trace (~220 LOC)
run_q1.py           end-to-end demo over the real sample
tests/test_q1.py    4 behavioural checks
```

```bash
python3 run_q1.py          # roles, resolved edges, upstream traces
python3 tests/test_q1.py   # 4 passing checks
```

What the run shows on the real sample (~340 LOC total, no dependencies):

- **Roles** inferred correctly: 5 ports, 6 refineries, 5 crackers.
- **Edge resolution** turning the 3 edgeless geometries into ~9 directed, commodity-typed,
  confidence-scored edges via the corridor model:
  - `naphtha`: Pernis / BP / Botlek refineries → Moerdijk cracker — **conf 0.66–0.80** (the
    three refineries actually sitting on the route, not the port an endpoint snap would pick).
  - `crude`: Rotterdam / Moerdijk import ports → Pernis & Botlek CDUs — **conf ≈ 0.4**,
    *kept but flagged* ("source inferred via port") because no oil field is in scope.
  - `ethylene`: Antwerp & Chemelot crackers → **UNRESOLVED** — produced on the route with
    no in-scope consumer, so the sink is left dangling rather than fabricated.
- **Trace** from the Moerdijk cracker now runs the full chain the data supports:
  `cracker ◀naphtha◀ {Pernis, BP, Botlek refineries} ◀crude◀ {Rotterdam, Moerdijk ports}`,
  stopping at the ports — the honest boundary where oil-field data would attach.
- **Oil-field slot-in** is verified by a test: adding a source node + crude link extends
  the trace to the field as a true source with **zero changes** to model or trace code.

The other four crackers remain isolated (no transport data reaches them) — precisely the
partial-data problem Q2 takes up.

---

# Q2 — Partial data: keeping the graph useful when infrastructure is invisible

The transport ground truth is **3 pipelines**; every barge and sea lane is missing, and so
are most pipelines. Q1 already separates *observed* from *inferred* edges with a confidence,
so Q2 is simply: **populate the inferred layer** — invent the plausible missing edges —
without letting them masquerade as fact.

The recipe (from the literature review): a cheap **distance prior** says what's *plausible*,
a **hard mode-feasibility gate** drops what's *impossible*, and a **low confidence tag** says
how much to trust it. Per mode:

- **Sea lanes** — ports are mutually sea-connected (one edge per port pair). Gate: both
  endpoints are ports.
- **Barges** — feed each inland consumer from its nearest port (naphtha → cracker, crude →
  refinery). Gate: commodity is barge-able and within a distance cap.
- **Ethylene is excluded from both** — it's a gas, dedicated-pipeline only.

Inferred edges get a deliberately low confidence (sea ×0.5, **barge ×0.4 — the lowest**),
because with no barge network *and* no river geometry we genuinely **cannot know** the barge
graph; we fall back to distance + commodity-feasibility + a coarse distance proxy for
navigability. That proxy is the honest weak spot, and it's flagged as such rather than
dressed up as a measurement.

`run_q2.py` writes **two maps** (nodes and edges only, no basemap):

- **`q2_observed.png`** — the real data as given: facility dots (crackers red, refineries
  navy, ports gold) + the **3 real pipeline geometries** drawn in their true shape (crude,
  naphtha, ethylene). This is literally what the package hands us — sparse.
- **`q2_inferred.png`** — the reconstruction: observed pipelines (solid orange) + inferred
  sea lanes (dark-blue) and barges (light-blue), **dashed**, opacity scaled by confidence.
  The payoff: all **5 crackers become connected** (vs the 1 reachable from observed data),
  including the inland Chemelot complex now fed by an inferred barge — and no illegal edges
  (no ethylene barge, no sea lane to an inland site). Ethylene pipes are omitted here: they
  are *product* lines leaving the crackers toward downstream derivative plants we don't model
  (an export, not a supply), so they never resolve to an edge.

Still out of scope (Q3): no flows — Q2 produces *which edges exist*, not how much moves.

```bash
python3 run_q2.py            # writes q2_observed.png + q2_inferred.png; prints edge counts
python3 tests/test_q2.py     # 3 passing checks
```

---

# Q3 — Scenario analysis: where the "what-if" lives

We don't own the solver — we own **its interface**. So a shock is expressed in the solver's
own first-class vocabulary, **capacities**, as a non-destructive **overlay on the solver
input**:

```
raw data (immutable)
   → build solver input  (nodes+capacities, edges, sources/sinks)
   → SHOCK = capacity overlay  (set chosen node/edge capacity → 0 or a fraction)   ← lives HERE
   → solve(input')                                                                 ← pure black box
   → diff(baseline, shock)
```

`baseline = solve(build(data))`, `shock = solve(with_shock(build(data)))`, then diff. Why
a capacity overlay rather than editing the graph or the data:

- **raw data stays immutable** — a shock is a hypothesis, not a correction to our records;
- **the solver stays a pure black box** — we only choose what to feed and what comes back;
- **capacity is native to the solver input**, so the shock speaks the solver's language;
- setting capacity to 0 is **reversible**, supports **partial derating** (a fraction, not
  just on/off), and keeps an **identical topology** baseline-vs-shock → the diff is a clean
  element-by-element comparison. (This is the FBA gene/reaction-knockout pattern.)

The two shock kinds map to two overlays: **facility offline** → zero that facility's node
capacities (`offline_facilities`); **region/mode impassable** → zero the capacity of the
affected edges (`blocked_modes`). The Strait of Hormuz is upstream of our slice, so the
in-scope analog is a **Rhine barge closure**.

We **define the output too** — not just per-edge flow but **per-sink fulfilment** — so
"which cracker starved" falls straight out of a diff. Per the agreed scope, the solver is a
**reachability stub** (a placeholder for the real most-likely-flow black box) and transport
is **uncapacitated** — the capacity field is used *only* as the shock lever. So today's
answer is *connectivity* ("who still gets supplied"), and it upgrades to quantitative
flow-stress the moment the real capacitated solver is dropped into the same interface.

`run_q3.py` shows it on the sample: baseline supplies all 5 crackers; **Antwerp port
offline** is *localized* (starves the 3 crackers fed by the Antwerp barge); a **Rhine barge
closure** is *systemic* (starves 4 of 5 — only Moerdijk survives, because it's the one
cracker fed by observed refinery *pipelines* rather than inferred barges).

```bash
python3 run_q3.py            # baseline + two shocks, with the diff (text)
python3 run_q3_map.py        # writes q3_shocks.png — baseline vs shocks, side by side
python3 tests/test_q3.py     # 4 passing checks
```

`q3_shocks.png` shows the three runs as maps: edges that stop carrying go grey/dotted, and
crackers that lose supply (plus offline facilities) are greyed with an ✗ — so the localized
(Antwerp) vs systemic (barge closure) contrast is visible at a glance.
