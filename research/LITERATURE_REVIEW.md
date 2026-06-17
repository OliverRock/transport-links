# Literature Review: Modelling Partially-Observable Flow Networks

*Exploratory survey for the Atmospheric AI connectivity take-home. The goal here is
**not** to propose a solution yet — it is to find how the underlying problem ("model
a complex system, understand its structure and how material moves through it, when
much of the graph is invisible") has been attacked in adjacent fields, and to extract
the transferable mathematical machinery and the tradeoffs each field has learned.*

---

## 0. The one-sentence framing that unifies everything

Strip the petrochemical domain away and the problem is:

> We observe **aggregate or boundary signals** about a network. We want to recover the
> **latent interior** — which edges exist, and how much flows along each. The map from
> interior to observation is **underdetermined**: many interiors explain the same
> observations. So we cannot *measure* the answer; we must *select* one, using a
> principle that encodes our assumptions.

Almost every field below is solving `y = A·x` (or a bilinear variant) where `y` is what
we see, `x` is the hidden flow/structure, and `A` is rank-deficient — infinitely many
`x` fit. **The entire intellectual content of each field is its choice of selection
principle and the priors it injects to make the problem well-posed.** Four principles
recur:

| Selection principle | "Pick the `x` that…" | Fields that use it |
|---|---|---|
| **Maximum entropy / minimum information** | …is least committal / most likely given marginals | IO reconstruction, OD-matrix estimation, gravity models |
| **Optimisation of a system objective** | …maximises a presumed goal (e.g. growth, throughput) | Flux balance analysis |
| **Sparsity / minimality** | …uses the fewest active edges/reactions | Compressed-sensing tomography, metabolic gap-filling |
| **Bayesian posterior** | …is most probable under an explicit generative prior | Bayesian MFA, Bayesian OD, generative link prediction |

Two sub-problems also recur and are worth separating cleanly, because the petrochemical
task contains **both**:

1. **Topology inference** — *which* edges exist (the barge/pipeline links we don't have).
2. **Flow/weight reconstruction** — *how much* moves on the edges we believe exist.

Different fields are strong at different halves. The synthesis at the end maps each half
of the take-home onto the field that solved it best.

---

## 1. Systems biology — metabolic networks *(the closest structural analogue)*

This is the field to steal from most aggressively, because a petrochemical supply chain
**is** a metabolic network at a different scale: units are reactions, commodities are
metabolites, conversions (crude → naphtha → ethylene) are stoichiometry, and nameplate
capacities are flux bounds.

### Core framework: Flux Balance Analysis (FBA)
- **Orth, Thiele & Palsson (2010), "What is flux balance analysis?", *Nature
  Biotechnology* 28:245–248.** The canonical primer. *[verified 3-0: FBA is a
  constraint-based, not kinetic, method for analysing metabolite flow; it rests on a
  **steady-state mass-balance assumption**.]*
- The model is `S·v = 0` (mass conservation at every node), with `v_min ≤ v ≤ v_max`
  (capacity bounds), maximising an objective `cᵀv`. This is a linear program. **It is
  almost exactly the "black-box solver" described in Q3 of the take-home** — given a
  graph with capacities and sources/sinks, return the most-likely per-edge flow.

### The partial-observability core
- **"Addressing uncertainty in genome-scale metabolic model reconstruction and
  analysis", *Genome Biology* (2021), 22:64.** *[verified 3-0]* The stoichiometric
  matrix is **almost always rank-deficient** relative to the number of reactions →
  an underdetermined system with an **infinite feasible flux space** that FBA alone
  cannot resolve. This is the exact mathematical situation we are in with missing
  transport edges.
- Same paper, *[verified 2-1]*: **no single objective function predicts fluxes best
  across all conditions** — i.e. "maximise growth"/"maximise throughput" is a *modelling
  choice*, not a law. Directly relevant warning for Q3: the solver's objective is an
  assumption we own, not ground truth.

### Gap-filling = topology inference for missing edges
When the reconstructed network can't carry flux from inputs to a required output, there's
a **gap** — a missing reaction. Gap-filling finds the smallest set of reactions (drawn
from a universal database) that restores consistency. This is *precisely* our
"infer the missing barge/pipeline links" problem.
- **GapFind / GapFill — Kumar, Dasika & Maranas (2007), "Optimization based automated
  curation of metabolic reconstructions", *BMC Bioinformatics*.** The original
  optimisation formulation (mixed-integer: minimise reactions added subject to
  flux-consistency).
- **fastGapFill — Thiele, Vlassis & Fleming (2014), *Bioinformatics* 30(17):2529.**
  An efficient method. *[verified 2-1: prior algorithms required
  "decompartmentalisation" to stay tractable, which **systematically under-estimates
  missing reactions by wrongly connecting reactions across compartments**.]* The lesson
  transfers: **respecting structural constraints (compartments) matters** — for us, the
  analogue is that a barge edge is only legal on a navigable river, a sea lane only
  between ports. Throwing those constraints away to make inference easy creates
  phantom edges.
- **MIRAGE — Vitkin & Shlomi (2012), *Genome Biology*.** *[verified 2-0: achieved
  41.9% precision / 24.3% recall on E. coli, **significantly better than random
  (P<10⁻¹⁶)**, by weighting candidate reactions with functional-genomics evidence.]*
  The transferable idea: **don't fill gaps uniformly — weight candidate edges by side
  evidence** (for us: distance, capacity, commodity compatibility, known corridors).

### Inferring interior flows from boundary measurements
- **BayFlux & ¹³C Metabolic Flux Analysis (PLoS Comput. Biol. 2023).** *(harvested,
  not adversarially verified)* Treats internal fluxes as **unobservable**, inferred from
  indirect boundary measurements (extracellular exchange + isotope-labelling patterns)
  via a Bayesian posterior `p(v|y) ∝ p(y|v)p(v)` sampled by MCMC. The key idea: when the
  LP is underdetermined, **add measurements that constrain the interior** (isotope
  tracing) rather than just asserting an objective. Our analogue: customs/throughput/
  AIS-ship-movement data are the "isotope tracers" that pin down interior commodity flow.

**Tradeoff this field teaches:** the feasible space is infinite; you buy uniqueness
either with a **strong objective assumption** (cheap, possibly wrong) or with **more
boundary measurements** (expensive, more faithful). And topology gaps can be filled, but
only as well as your candidate database and your respect for structural constraints.

---

## 2. Economics — input-output analysis & supply-chain reconstruction *(the closest problem analogue)*

If metabolic networks are the closest *structural* analogue, firm-level supply-chain
reconstruction is the closest *problem* analogue: economists routinely have to rebuild a
production network where **they know the nodes and some aggregates but not the edges.**

### Foundational framework: Leontief input-output
- **"Measuring Global Value Chains", NBER w24027 (Johnson, 2018; *Annual Review of
  Economics*).** *(harvested)* The Leontief inverse `[I−A]⁻¹` propagates final demand
  back through all upstream tiers — this is *exactly* the "trace naphtha back to the oil
  field" operation in Q1, expressed in matrix form. Also documents the honest reality:
  global IO tables are stitched from national tables using bilateral trade and
  **proportionality assumptions** because import-use tables don't separate domestic vs
  imported inputs. (Imperfect-but-validated: firm-level data correlates ~0.68 unweighted /
  ~0.87 value-weighted with published coefficients.) **Takeaway: even the "ground-truth"
  IO tables are themselves reconstructions** — partial observability is the norm, not the
  exception.

### Network reconstruction from partial information
This is a coherent, recent subfield and the single most on-point cluster found:
- **"Reconstructing supply networks" (review, 2023; arXiv:2310.00446).** *(harvested)*
  Frames the whole task: infer production-network topology (firms = nodes,
  supplier–customer = edges) from **partial, aggregate, or indirect** observations. Best
  single entry point to the literature.
- **"Reconstructing firm-level input-output networks from partial information"
  (arXiv:2304.00081).** *(harvested)* Often you observe only **edge existence, not
  transaction value** — a partial-observability problem where **weights are the hidden
  variable**. Solves it with **maximum-entropy** reconstruction constrained by observed
  binary structure + aggregate financial disclosures.
- **"Reconstructing firm-level interactions in the Dutch input–output network from
  production constraints", *Scientific Reports* (2022; s41598-022-13996-3).**
  *(harvested)* Introduces the **stripe-corrected gravity model**. Two transferable
  findings: (a) plain **degree-corrected gravity models produce networks that are too
  homogeneous** vs reality — a real bias of the naive approach; (b) accuracy **improves
  monotonically as you condition on finer sector/product resolution.**
- **"Inferring firm-level supply chain networks with realistic systemic risk from
  industry sector-level data" (arXiv:2408.02467).** *(harvested)* Quantifies the
  accuracy-vs-data tradeoff cleanly: models that preserve **firm-specific,
  sector-disaggregated in-strength** recover systemic-risk indices at **Pearson ≈ 0.8**,
  vs ≈0.7 / ≈0.4 for coarser models. **The minimal sufficient input is "how much each
  node buys from each commodity class," not just total in/out volume.**

**The gravity model** (edge likelihood ∝ `mass_i · mass_j / distance^β`) is the workhorse
here and maps directly onto our transport problem: probability of a link between two
facilities scales with their capacities and decays with distance — modulated by
mode-feasibility (barge needs a river, sea lane needs two ports).

**Tradeoff this field teaches:** maximum-entropy gives you the *least-biased* network
consistent with what you know, and you can dial fidelity up by adding finer marginal
constraints — but naive/coarse constraints produce systematically **too-homogeneous,
biased** reconstructions. Resolution of the constraints, not the cleverness of the
algorithm, is what buys accuracy.

---

## 3. Computer science — network tomography *(the rigorous theory of "boundary in, interior out")*

Network tomography is the purest formalisation of inferring interior link states from
only **edge/end-to-end** measurements — born in networking, but the theory is
domain-agnostic.
- **Vardi (1996), "Network Tomography: Estimating Source-Destination Traffic Intensities
  from Link Data", *JASA* 91:365–377.** *(seminal; coined the term)* Origin–destination
  traffic as a Poisson inference problem from link counts — `y = A·x`, `A` a routing
  matrix, `x` the hidden OD intensities.
- **Castro, Coates, Liang, Nowak & Yu (2004), "Network Tomography: Recent Developments",
  *Statistical Science* 19(3):499–517.** *(harvested)* The standard survey. Splits the
  field into (i) link-level inference from path measurements and (ii) path/OD inference
  from link measurements, and — crucially — establishes that the linear systems are
  **fundamentally under-constrained**, requiring statistical assumptions (e.g. a
  parametric traffic model) to identify a solution.
- **"Network Tomography: Identifiability and Fourier-Domain Estimation"
  (arXiv:0712.3618).** *(harvested)* Tackles **identifiability** head-on: *when* can the
  interior even be recovered in principle? The key conceptual export to our problem —
  before tuning an inference method, ask whether the data we have can determine the
  answer *at all*, or whether we are merely choosing a prior.
- **Compressed-sensing bridge — "Compressive Sensing over Graphs" (arXiv:1008.0919) and
  "Sparse Recovery with Graph Constraints" (arXiv:1207.2829).** *(harvested)* If the
  hidden interior is **sparse** (few links are congested / active), you can recover it
  from far fewer measurements than the dimension would suggest, via L1 minimisation —
  *provided measurements are designed well.* This is the principled answer to "how few
  probes do I need."

**Tradeoff this field teaches:** there's a hard **identifiability frontier** — with only
passive boundary data the interior is often unrecoverable, and the fix is either **active
probing** (inject measurements you control) or a **structural prior** (sparsity). It also
gives us the honesty check: distinguish "the data determines this" from "my prior
determines this."

---

## 4. Computer science — link prediction & graph completion *(topology inference, the missing-edges half)*

Where tomography assumes the topology and infers flows, link prediction assumes partial
topology and infers the **missing edges** — directly our "no barge data, partial
pipelines" problem.
- **Liben-Nowell & Kleinberg (2007), "The Link-Prediction Problem for Social Networks",
  *JASIST*.** *(seminal)* Establishes link prediction from structural proximity
  (common neighbours, Katz, etc.).
- **Clauset, Moore & Newman (2008), "Hierarchical structure and the prediction of missing
  links in networks", *Nature* 453:98–101.** *(seminal; the canonical
  partial-observability paper)* Fits a **hierarchical generative model** to the observed
  graph, then predicts missing edges from the inferred hierarchy. The transferable idea:
  **learn the latent organising structure** (here: geography + commodity tiers) **and let
  it predict the edges you can't see.**
- **"Link prediction for partially observed networks" (arXiv:1301.7047)** and the survey
  **"Link Prediction in Social Networks: the State-of-the-Art" (arXiv:1411.5118).**
  *(harvested)* Methods specifically for when only a sample of edges is observed.
- **"Graph Learning Under Partial Observability" (arXiv:1912.08465)** and **"Network
  Topology Inference from Smooth Signals Under Partial Observability"
  (arXiv:2410.05707).** *(harvested)* Infer topology when **some nodes/edges are entirely
  hidden** — the strongest form of our problem (a whole transport mode missing).
- **Knowledge-graph completion (survey, arXiv:2007.12374).** *(harvested)* The same task
  viewed as completing typed, directed relations — relevant because our graph is **typed**
  (unit types, commodity-specific edges) and completion should respect type constraints
  (you can't predict a "barge" edge where there is no river).

**Tradeoff this field teaches:** structural/embedding methods predict missing edges
cheaply but degrade as the observed fraction shrinks, and they happily hallucinate edges
that violate domain constraints unless those constraints are encoded as hard rules. For
us: **type/feasibility constraints must be hard filters on the candidate edge set**, not
soft features.

---

## 5. Transportation — origin–destination (OD) matrix estimation *(the most operationally similar precedent)*

Transport planners have solved a strikingly similar problem for 40 years: reconstruct the
full origin→destination flow matrix from **sparse traffic counts on a subset of links.**
- **Van Zuylen & Willumsen (1980), "The most likely trip matrix estimated from traffic
  counts", *Transportation Research Part B* 14:281–293.** *(seminal)* The
  **maximum-entropy / minimum-information** OD estimator: among all OD matrices
  consistent with observed counts, choose the most likely (least-committal). This is the
  *exact* principle the IO-reconstruction people rediscovered, and the one I'd lean on for
  filling unobserved transport flows.
- **Cascetta (1984) — Generalised Least Squares OD estimation**, and **Abrahamsson (1998),
  "Estimation of Origin-Destination Matrices Using Traffic Counts — A Literature Survey",
  IIASA IR-98-021.** *(harvested; the survey)* Maps the whole methodological space and its
  data requirements.
- **"Bayesian inference on dynamic linear models of day-to-day origin-destination flows
  in transportation networks" (arXiv:1608.06682).** *(harvested)* The Bayesian/temporal
  treatment — fuse a prior OD matrix with incoming observations over time. Relevant if we
  ever get a trickle of throughput/shipping observations and want to update beliefs rather
  than re-solve from scratch.

**Tradeoff this field teaches:** you almost always need a **prior/target matrix** (a "this
is roughly what flows look like" seed) to regularise the under-determined estimate; the
quality of that seed dominates the quality of the estimate. For us the seed is the gravity
model (capacity × distance-decay).

---

## 6. Synthesis — how this maps onto the three take-home questions

The literature converges on a clean division of labour that lines up one-to-one with the
take-home:

**Q1 — Domain modelling & upstream tracing.**
Model it as a **typed, directed flow network with stoichiometric conversion at nodes** —
i.e. a metabolic model (§1). Facilities are containers; **units are the reactions**
(crude_distillation: crude → naphtha+products; steam_cracker: naphtha → ethylene);
commodities are the metabolites; transport edges are transfer reactions. Upstream tracing
"back to the oil field" is the **Leontief inverse `[I−A]⁻¹`** (§2) — propagating a
cracker's demand back through the conversion matrix. Oil-field sourcing slots in as the
source layer of the same matrix (`v_in` exchange reactions), exactly as FBA handles
medium uptake.

**Q2 — Partial data (no barges, partial pipelines): keep the graph useful when edges are
invisible.** This is **topology inference + flow reconstruction under partial
observability**, and the fields agree on the recipe:
1. Generate a **candidate edge set** from a **gravity model** (§2/§5): link likelihood ∝
   capacity×capacity / distance^β.
2. Apply **mode-feasibility as hard constraints** (the compartmentalisation lesson from
   §1 and the typed-completion lesson from §4): barge edges only along navigable rivers
   between river-reachable facilities; sea lanes only port↔port; pipelines snap to/extend
   known geometries.
3. Fill the flows with **maximum-entropy / minimum-information** estimation (§2/§5) — the
   least-biased flows consistent with capacities and known sources/sinks.
4. Be explicit about the **identifiability frontier** (§3): label every edge by
   derivation (`OBSERVED` vs `INFERRED`) and don't claim more certainty than the data
   supports. Reproducing the example map = drawing observed pipelines + gravity-inferred
   sea lanes between the ports + gravity-inferred barge links along the Rhine/Scheldt
   corridor, styled by confidence.

**Q3 — Scenario / what-if analysis.** This is **textbook FBA perturbation analysis** (§1):
a facility going offline is a **reaction knockout** (set that node/edge bound to 0); the
Strait of Hormuz closing is a **region knockout** (zero every edge crossing that
geometry). Re-solve, then do **differential flux analysis** (baseline vs post-shock) — the
same comparison economists use for **systemic-risk shock propagation** (§2). The cleanest
architecture, consistent across all fields: **the intervention lives in graph
construction, not in the solver.** You build a shocked graph by masking nodes/edges, hand
both baseline and shocked graphs to the *same* black-box solver, and diff the per-edge
flows. The solver stays a pure function; scenarios are just different inputs — which makes
baseline-vs-shock comparison trivial and reproducible.

**The big idea to carry into the design:** the petrochemical supply chain is a metabolic
network whose transport layer is observed like a tomography/OD problem. So borrow FBA's
node/conversion model and knockout analysis (§1), the Leontief inverse for tracing (§2),
and the maximum-entropy + gravity + hard-feasibility recipe for inventing the edges we
can't see (§2/§4/§5) — while using tomography's identifiability discipline (§3) to stay
honest about what is inferred vs observed.

---

## Appendix — provenance & confidence

This review was produced by a fan-out web-research run (6 angles, 33 primary sources
fetched, 124 claims extracted). The adversarial-verification and auto-synthesis stages
were **cut short by a session/usage limit**, so only 6 claims completed the 3-vote
verification before the run stopped. Confidence labels above mean:

- ***[verified N-M]*** — passed adversarial verification (N confirm / M refute votes).
  These are the 6 FBA / metabolic-modelling claims.
- ***(harvested)*** — extracted verbatim from the fetched primary source with a
  supporting quote, but **not** independently re-verified (the verifier agents hit the
  limit mid-run; a `0-0` vote in the raw output means "verifier crashed," not "refuted").
  Treat as reliable-but-unconfirmed.
- ***(seminal)*** — foundational papers I added from domain knowledge to fill obvious
  gaps the search missed (Vardi 1996; Liben-Nowell & Kleinberg 2007; Clauset–Moore–Newman
  2008; Van Zuylen–Willumsen 1980; Cascetta 1984). Paper identities for all fetched URLs
  were confirmed directly against the source pages.

Two claims were *genuinely* refuted in verification and have been **corrected** in the
text: (a) that fastGapFill was "the first" compartmentalised gap-filler — it isn't; the
GapFind/GapFill lineage (Maranas group) predates it; (b) an over-strong claim that
gap-filling is *fundamentally* bounded by its reaction database. Both are reflected above.

**Next step if you want the full verified version:** after the usage limit resets, re-run
the verify+synthesis tail over the remaining 99 harvested claims. The raw harvest
(all 124 claims + 33 sources) is preserved in the workflow output file.
