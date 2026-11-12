"""Shared look of the GF180 EEG figures (figs.py, figs_perf.py): colours, matplotlib settings
and the page frame (title, subtitle, note, the chip version at the top right)."""
import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# The chip the figures show: the assembly round of the docs ("N 回目のチップ"). It names the
# folder documentation/figures/gf180/<CHIP>_<CHIP_DATE>/viz/, the files gf180_viz_<CHIP>_NN_*.png
# and the label on every figure. A new round gets a new folder and a full set of figures.
CHIP, CHIP_DATE = "r10", "20261109"
CHIP_LABEL = "Chip r10 (tenth assembly, 9 Nov 2026)"

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


def wrap(text, width_in, size):
    """Break text into lines no wider than width_in inches at size points (its own line breaks kept):
    a long note would otherwise widen the saved figure (savefig.bbox tight) past its plots."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextToPath
    prop, t2p = FontProperties(size=size), TextToPath()
    fits = lambda s: t2p.get_text_width_height_descent(s, prop, ismath=False)[0] <= width_in * 72  # noqa: E731
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            if line and not fits(line + " " + word):
                out.append(line)
                line = word
            else:
                line = f"{line} {word}" if line else word
        out.append(line)
    return "\n".join(out)


def figure(w, h, title, sub, note=None):
    fig = plt.figure(figsize=(w, h), layout="constrained")
    sub = wrap(sub, w * 0.985, 9.5)
    ns = sub.count("\n")                            # a subtitle too long for one line takes the next, 9.5 pt each
    top = (0.80 + 0.16 * ns) / h
    if note:
        note = wrap(note, w * 0.985, 8)
        extra = 0.133 * max(0, note.count("\n") - 1)   # a third line and more: 8 pt at 1.2 line spacing each
    bot = (0.40 + extra) / h if note else 0.03
    fig.get_layout_engine().set(rect=(0.0, bot, 1.0, 1.0 - top - bot), w_pad=0.08, h_pad=0.08)
    fig.text(0.006, 1 - 0.30 / h, title, fontsize=14.5, fontweight="semibold", color=INK, ha="left", va="center")
    fig.text(0.994, 1 - 0.30 / h, CHIP_LABEL, fontsize=9.5, fontweight="medium", color=ACCENT, ha="right", va="center")
    fig.text(0.006, 1 - (0.58 + 0.08 * ns) / h, sub, fontsize=9.5, color=MUTED, ha="left", va="center")
    if note:
        fig.text(0.006, (0.16 + extra / 2) / h, note, fontsize=8, color=LIGHT, ha="left", va="center")
    return fig
