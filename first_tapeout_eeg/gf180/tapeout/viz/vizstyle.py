"""Shared look of the GF180 EEG figures (figs.py, figs_perf.py): colours, matplotlib settings
and the page frame (title, subtitle, note)."""
import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, INK2, MUTED, LIGHT, HAIR = "#0f172a", "#334155", "#64748b", "#94a3b8", "#e2e8f0"
ACCENT = "#4f46e5"
OK, WARN, BAD = "#15803d", "#b45309", "#b91c1c"

RC = {
    "font.family": "Helvetica Neue", "font.size": 9.5, "text.color": INK,
    "axes.titlesize": 10.5, "axes.titleweight": "medium", "axes.titlelocation": "left", "axes.titlepad": 8,
    "axes.labelsize": 9, "axes.labelcolor": INK2, "axes.edgecolor": "#cbd5e1", "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.axisbelow": True,
    "grid.color": HAIR, "grid.linewidth": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
    "xtick.major.size": 3, "ytick.major.size": 3, "xtick.major.width": 0.7, "ytick.major.width": 0.7,
    "legend.frameon": False, "legend.fontsize": 8.5, "axes.unicode_minus": True,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    "savefig.dpi": 220, "savefig.bbox": "tight", "savefig.pad_inches": 0.25,
}


def apply():
    mpl.rcParams.update(RC)


apply()


def figure(w, h, title, sub, note=None):
    fig = plt.figure(figsize=(w, h), layout="constrained")
    top = 0.80 / h
    bot = 0.40 / h if note else 0.03
    fig.get_layout_engine().set(rect=(0.0, bot, 1.0, 1.0 - top - bot), w_pad=0.08, h_pad=0.08)
    fig.text(0.006, 1 - 0.30 / h, title, fontsize=14.5, fontweight="semibold", color=INK, ha="left", va="center")
    fig.text(0.006, 1 - 0.58 / h, sub, fontsize=9.5, color=MUTED, ha="left", va="center")
    if note:
        fig.text(0.006, 0.16 / h, note, fontsize=8, color=LIGHT, ha="left", va="center")
    return fig
