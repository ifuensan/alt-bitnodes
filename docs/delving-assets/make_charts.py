import json
import datetime as dt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator

# --- palette (dataviz reference, light mode) ---
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK,
    "axes.edgecolor": BASELINE,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.labelcolor": INK2,
})

OUT = "/tmp/claude-1000/-mnt-datos-home-data-Work-hacknodes-myprojects-research-bitnodes-dashboard/ce51cbfc-93ca-40f8-9cff-f8f7658f2751/scratchpad"

with open(f"{OUT}/egress_daily.json") as f:
    rows = json.load(f)
days = [dt.date.fromisoformat(r["d"]).day for r in rows]
gb = [r["gb"] for r in rows]

# ---------------- Chart A: daily egress bars ----------------
fig, ax = plt.subplots(figsize=(10, 4.6), dpi=200)
ax.bar(days, gb, width=0.78, color=BLUE, zorder=3)

ax.set_title("Daily EC2 internet egress — July 2026", fontsize=13,
             fontweight="bold", loc="left", color=INK, pad=42)
ax.text(0, 1.065, "us-east-1 DataTransfer-Out, billed at \\$0.09/GB — the plateau is ~\\$22/day",
        transform=ax.transAxes, fontsize=9, color=INK2)

events = [(17, "①"), (19, "②"), (23, "③")]
for d, mark in events:
    ax.axvline(d - 0.5, color=MUTED, lw=1, ls=(0, (4, 3)), zorder=2)
    ax.text(d - 0.5, 368, mark, ha="center", fontsize=11, color=INK2)
ax.text(1, 407,
        "① Jul 17 · 24k socket slots (stage 4)      "
        "② Jul 19 · I2P live + Tor pool of 9 (stages 5–6)      "
        "③ Jul 23 · UseEntryGuards 0 (stage 8)",
        fontsize=8.2, color=INK2, va="top")

peak_i = gb.index(max(gb))
ax.annotate(f"{max(gb):.0f} GB", (days[peak_i], max(gb) + 5),
            ha="center", fontsize=8.5, color=INK2)
ax.text(31.9, 345, "Aug 1: crawler stopped → ~0", fontsize=8.5,
        color=INK2, ha="right")

ax.set_xlim(0.3, 32.2)
ax.set_ylim(0, 410)
ax.set_ylabel("GB / day", fontsize=9)
ax.set_xticks([1, 8, 15, 22, 29])
ax.set_xticklabels(["Jul 1", "Jul 8", "Jul 15", "Jul 22", "Jul 29"], fontsize=9)
ax.yaxis.set_major_locator(FixedLocator([0, 100, 200, 300]))
ax.tick_params(length=0)
ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(BASELINE)
fig.tight_layout()
fig.savefig(f"{OUT}/chart_egress_daily.png", bbox_inches="tight")
plt.close(fig)

# ---------------- Chart B: composition stacked bar ----------------
fig, ax = plt.subplots(figsize=(10, 2.5), dpi=200)
segs = [("I2P tunnel machinery", 55.0, BLUE),
        ("Tor circuit machinery", 44.9, ORANGE),
        ("Bitcoin protocol", 0.1, AQUA)]
left = 0.0
for name, val, color in segs:
    ax.barh(0, val, left=left, height=0.55, color=color,
            edgecolor=SURFACE, linewidth=2, zorder=3)
    left += val

fig.text(0.008, 0.94, "Where the egress actually goes", fontsize=13,
         fontweight="bold", color=INK, va="top")
fig.text(0.008, 0.80, "Share of ~356 GB/day · measured 2026-08-01 via per-process "
                      "TCP bytes_sent deltas + i2pd router console",
         fontsize=9, color=INK2, va="top")

ax.text(27.5, 0, "I2P — 55%", ha="center", va="center",
        fontsize=10.5, color="#ffffff", fontweight="bold")
ax.text(77.4, 0, "Tor — 45%", ha="center", va="center",
        fontsize=10.5, color="#ffffff", fontweight="bold")
ax.annotate("Bitcoin protocol — 0.1%", xy=(99.95, 0.28), xytext=(82, 0.85),
            fontsize=9, color=INK2,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=1))
ax.text(0, -0.60, "I2P: tunnel builds at 67% success, leaseset lookups, NetDb, "
                  "SSU2 — zero transit for other routers",
        fontsize=8, color=MUTED)
ax.text(0, -0.88, "Tor: ~1,000 fresh TLS connections/min — the price of "
                  "UseEntryGuards 0",
        fontsize=8, color=MUTED)

ax.set_xlim(0, 100)
ax.set_ylim(-1.05, 1.1)
ax.axis("off")
fig.subplots_adjust(top=0.60, bottom=0.04, left=0.008, right=0.995)
fig.savefig(f"{OUT}/chart_egress_composition.png", bbox_inches="tight")
plt.close(fig)

# ---------------- Chart C: price of a node count ----------------
fig, ax = plt.subplots(figsize=(7.5, 5), dpi=200)
pts = [(4.2, 0.30, "pre-scale baseline", (12, -4)),
       (11.6, 1.60, "24k socket slots\nclearnet complete", (12, -12)),
       (13.5, 15.0, "I2P live +\nTor pool of 9", (-78, -12)),
       (22.1, 22.0, "UseEntryGuards 0\n~22k nodes", (-14, -46))]
xs = [p[0] for p in pts]
ys = [p[1] for p in pts]
ax.plot(xs, ys, color=BLUE, lw=2, zorder=3)
ax.scatter(xs, ys, s=64, color=BLUE, zorder=4)
for x, y, label, (dx, dy) in pts:
    nlines = label.count("\n") + 1
    val = f"${y:,.2f}/day" if y < 10 else f"${y:,.0f}/day"
    ax.annotate(val, (x, y), xytext=(dx, dy + 11 * nlines + 4),
                textcoords="offset points",
                fontsize=9, color=INK, fontweight="bold")
    ax.annotate(label, (x, y), xytext=(dx, dy), textcoords="offset points",
                fontsize=8, color=INK2, va="top")

ax.set_yscale("log")
ax.set_title("The price of a node count", fontsize=13, fontweight="bold",
             loc="left", color=INK, pad=26)
ax.text(0, 1.06, "Egress cost vs reachable nodes — clearnet is nearly free; "
                 "overlay visibility costs 70× more",
        transform=ax.transAxes, fontsize=9, color=INK2)
ax.set_xlabel("reachable nodes (thousands)", fontsize=9)
ax.set_ylabel("egress cost, $/day (log scale)", fontsize=9)
ax.set_xlim(2, 27)
ax.set_ylim(0.2, 40)
ax.yaxis.set_major_locator(FixedLocator([0.3, 1, 3, 10, 30]))
ax.yaxis.set_major_formatter(lambda v, _: f"${v:g}")
ax.minorticks_off()
ax.tick_params(length=0)
ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(BASELINE)
fig.tight_layout()
fig.savefig(f"{OUT}/chart_cost_per_nodes.png", bbox_inches="tight")
plt.close(fig)

print("done")
