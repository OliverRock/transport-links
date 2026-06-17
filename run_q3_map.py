"""Q3 maps: baseline vs each shock, side by side. Edges that stop carrying go grey/dotted;
crackers that lose supply (and offline facilities) are greyed with an x. Writes q3_shocks.png.

    python3 run_q3_map.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path

from petrochem import (build_edges, build_solver_input, facility_roles,
                       infer_transport_edges, load, stub_solve, with_shock)

DATA = Path(__file__).parent / "take_home_data"
ROLE_COLOR = {"cracker": "red", "refinery": "navy", "port": "gold"}
MODE_COLOR = {"pipeline": "orange", "sea": "darkblue", "barge": "deepskyblue"}


def main() -> None:
    facilities, units, links = load(DATA)
    edges = build_edges(facilities, units, links) + infer_transport_edges(facilities, units)
    si = build_solver_input(units, edges)

    fac = {f.id: f for f in facilities}
    unit_fac = {u.id: u.facility_id for u in units}
    cracker_unit = {u.facility_id: u.id for u in units if u.unit_type == "steam_cracker"}

    def role(f):
        r = facility_roles(u.unit_type for u in units if u.facility_id == f.id)
        return "cracker" if "cracker" in r else "refinery" if "refinery" in r else "port"

    def panel(ax, shocked, title):
        flows, ful = stub_solve(shocked)
        for e, flow in zip(shocked.edges, flows):
            a, b = fac[unit_fac[e.from_unit]], fac[unit_fac[e.to_unit]]
            if flow > 0:
                ax.plot([a.lon, b.lon], [a.lat, b.lat], color=MODE_COLOR[e.mode],
                        lw=1.3, alpha=0.85, zorder=1)
            else:  # edge gone dark under the shock
                ax.plot([a.lon, b.lon], [a.lat, b.lat], color="0.8", lw=0.8,
                        ls=":", alpha=0.7, zorder=0)
        for f in facilities:
            r = role(f)
            offline = all(shocked.node_capacity[u.id] <= 0 for u in units if u.facility_id == f.id)
            starved = r == "cracker" and ful.get(cracker_unit[f.id], 0) == 0
            dead = offline or starved
            ax.scatter(f.lon, f.lat, c="0.7" if dead else ROLE_COLOR[r],
                       s=70, edgecolor="black", linewidth=0.5, zorder=3)
            if dead:
                ax.scatter(f.lon, f.lat, marker="x", c="black", s=40, linewidths=1.3, zorder=4)
        ax.set_title(title, fontsize=10)
        ax.set_xticks([]); ax.set_yticks([])

    antwerp = next(f.id for f in facilities if f.name == "Antwerp [BE]")
    runs = [
        ("Baseline — all 5 crackers supplied", si),
        ("Antwerp port offline (localized)", with_shock(si, offline_facilities={antwerp})),
        ("Rhine barge closure (systemic)", with_shock(si, blocked_modes={"barge"})),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), sharex=True, sharey=True)
    for ax, (title, shocked) in zip(axes, runs):
        panel(ax, shocked, title)

    handles = (
        [Line2D([], [], marker="o", color="w", markerfacecolor=c, markeredgecolor="k",
                markersize=9, label=r) for r, c in ROLE_COLOR.items()]
        + [Line2D([], [], color=c, lw=2, label=m) for m, c in MODE_COLOR.items()]
        + [Line2D([], [], color="0.8", lw=2, ls=":", label="no flow (dark)"),
           Line2D([], [], marker="x", color="k", lw=0, label="offline / starved")]
    )
    axes[0].legend(handles=handles, loc="upper left", fontsize=7, framealpha=0.9)
    fig.suptitle("Q3 — baseline vs shocks   (grey = no flow / starved cracker)", fontsize=13)
    fig.tight_layout()
    fig.savefig("q3_shocks.png", dpi=130)
    print("wrote q3_shocks.png")


if __name__ == "__main__":
    main()
