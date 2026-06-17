"""Q2 demo: two maps from the sample data.

  q2_observed.png  — the real data as given: facilities + the 3 real pipeline geometries.
  q2_inferred.png  — the reconstruction: observed (solid) + inferred sea lanes & barges
                     (dashed) that make the graph useful. Ethylene pipes omitted here
                     (product lines with no in-scope sink).

Nodes and edges only — no basemap, rivers, or coastlines.

    python3 run_q2.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path

from petrochem import build_edges, facility_roles, infer_transport_edges, load

DATA = Path(__file__).parent / "take_home_data"

ROLE_COLOR = {"cracker": "red", "refinery": "navy", "port": "gold"}          # facility dots
MODE_COLOR = {"pipeline": "orange", "sea": "darkblue", "barge": "deepskyblue"}  # inferred view
COMMODITY_COLOR = {"crude": "saddlebrown", "naphtha": "seagreen", "ethylene": "purple"}


def main() -> None:
    facilities, units, links = load(DATA)
    observed = build_edges(facilities, units, links)
    inferred = infer_transport_edges(facilities, units)
    fac = {f.id: f for f in facilities}
    fac_of_unit = {u.id: u.facility_id for u in units}

    def role(f):
        r = facility_roles(u.unit_type for u in units if u.facility_id == f.id)
        return "cracker" if "cracker" in r else "refinery" if "refinery" in r else "port"

    # shared axis range from the full observed extent (facilities + all pipeline geometry),
    # so both maps line up for direct comparison
    xs = [f.lon for f in facilities] + [p[0] for l in links for s in l.geometry for p in s]
    ys = [f.lat for f in facilities] + [p[1] for l in links for s in l.geometry for p in s]
    mx, my = (max(xs) - min(xs)) * 0.05, (max(ys) - min(ys)) * 0.05
    xlim, ylim = (min(xs) - mx, max(xs) + mx), (min(ys) - my, max(ys) + my)

    def draw_nodes(ax):
        for f in facilities:
            ax.scatter(f.lon, f.lat, c=ROLE_COLOR[role(f)], s=70,
                       edgecolor="black", linewidth=0.5, zorder=3)
            ax.annotate(f.name, (f.lon, f.lat), textcoords="offset points",
                        xytext=(5, 4), fontsize=6.5, zorder=4)
        ax.set_xlabel("lon"); ax.set_ylabel("lat")
        ax.set_xlim(xlim); ax.set_ylim(ylim)

    role_handles = [Line2D([], [], marker="o", color="w", markerfacecolor=c,
                           markeredgecolor="k", markersize=9, label=r)
                    for r, c in ROLE_COLOR.items()]

    # --- Plot 1: the real data as given (facilities + real pipeline geometries) ---
    fig, ax = plt.subplots(figsize=(9, 9))
    for link in links:
        for seg in link.geometry:
            ax.plot([p[0] for p in seg], [p[1] for p in seg],
                    color=COMMODITY_COLOR[link.commodity], linewidth=1.6, alpha=0.85, zorder=1)
    draw_nodes(ax)
    ax.legend(handles=role_handles
              + [Line2D([], [], color=c, lw=2, label=f"{k} pipeline")
                 for k, c in COMMODITY_COLOR.items()],
              loc="upper left", fontsize=8, framealpha=0.9)
    ax.set_title("Observed data (as given): facilities + the 3 real pipelines")
    fig.tight_layout(); fig.savefig("q2_observed.png", dpi=130)

    # --- Plot 2: the inferred reconstruction (no ethylene) ---
    fig, ax = plt.subplots(figsize=(9, 9))
    for edges, ls in [(observed, "-"), (inferred, "--")]:
        for e in edges:
            if not e.resolved:
                continue
            a, b = fac[fac_of_unit[e.from_unit]], fac[fac_of_unit[e.to_unit]]
            ax.plot([a.lon, b.lon], [a.lat, b.lat], color=MODE_COLOR[e.mode],
                    linestyle=ls, linewidth=1.6, alpha=0.25 + 0.65 * e.confidence, zorder=1)
    draw_nodes(ax)
    ax.legend(handles=role_handles
              + [Line2D([], [], color=c, lw=2, label=m) for m, c in MODE_COLOR.items()]
              + [Line2D([], [], color="gray", lw=2, ls="-", label="observed"),
                 Line2D([], [], color="gray", lw=2, ls="--", label="inferred")],
              loc="upper left", fontsize=8, framealpha=0.9)
    ax.set_title("Reconstructed graph: observed + inferred (sea lanes, barges)")
    fig.tight_layout(); fig.savefig("q2_inferred.png", dpi=130)

    print(f"observed edges: {sum(e.resolved for e in observed)} | "
          f"inferred: {len(inferred)} ({sum(e.mode=='sea' for e in inferred)} sea, "
          f"{sum(e.mode=='barge' for e in inferred)} barge)")
    print("wrote q2_observed.png and q2_inferred.png")


if __name__ == "__main__":
    main()
