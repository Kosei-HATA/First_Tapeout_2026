#!/usr/bin/env python3
"""GF180 Half Height chip area by function, 2026-10-22 estimate.

Block areas (low/high, mm2) are documentation/gf180_area_estimate_20261021.md with the
2026-10-22 changes:
  * AFE MOS +0.21..0.35 mm2 (new AFE configuration, documentation/gf180_afe_noise_20261022.md)
  * AFE output hold capacitors 2 x 30 pF, +0.03 mm2
  * DAC2 as the MOS current-steering DAC with stage 2 scaled x10
  * quantizer kept at its estimate range; its designed estimate is 0.085 mm2
    (documentation/gf180_quantizer_20261022.md)
Routing and space between blocks: +15 % (low) / +25 % (high), as in the estimate.
The chart uses the midpoint of each range; the whiskers show low..high.
Die and core are the wafer.space 1x0.5 slot (gf180/floorplan_half_height.py).

Writes documentation/figures/gf180/plan_20261022/gf180_area_by_function_20261022.svg and prints the table.
Run: python3 gf180/area_by_function.py
"""
import os
from xml.sax.saxutils import escape

DIE = 3.932 * 2.531
CORE = 3.048 * 1.647
ROUTE = (0.15, 0.25)

# function key -> (label, light color, dark color): dataviz reference palette, slots 1-4
FUNCS = {
    "afe": ("AFE", "#2a78d6", "#3987e5"),
    "adc": ("ADC", "#eb6834", "#d95926"),
    "sup": ("支援回路", "#1baf7a", "#199e70"),
    "dig": ("デジタル", "#eda100", "#c98500"),
}
# (function, component, low, high) in mm2
ITEMS = [
    ("afe", "AFE の MOS（増幅器、入出力 TG、ブースト段）", 0.404 + 0.21, 0.673 + 0.35),
    ("afe", "AFE の MIM（Cin、Cf、Cpf、保持容量）", 0.733 + 0.03, 0.818 + 0.03),
    ("adc", "ADC の積分容量 C1（MIM）", 0.773, 0.863),
    ("adc", "ADC の OTA1（MOS）", 0.321, 0.535),
    ("adc", "ADC の OTA2（MOS）", 0.008, 0.013),
    ("adc", "OTA の補償容量（MIM）", 0.022, 0.024),
    ("adc", "RIN・R21・DAC1 の抵抗", 0.067, 0.082),
    ("adc", "DAC2（MOS 電流 DAC と C2）", 0.034, 0.049),
    ("adc", "量子化器", 0.050, 0.120),
    ("adc", "DAC スイッチとドライバ", 0.010, 0.030),
    ("sup", "バイアス・VCM・基準", 0.050, 0.150),
    ("sup", "クロックドライバ", 0.005, 0.020),
    ("sup", "電極 DC サーボ（未設計）", 0.050, 0.200),
    ("sup", "デカップリング", 0.100, 0.250),
    ("dig", "デジタル（CIC、DWA、FIFO、SPI、レジスタ）", 0.250, 0.400),
]
GRAYS = {  # non-function area: (label, light, dark)
    "route": ("配線・ブロック間", "#c3c2b7", "#5a5955"),
    "spare": ("予備", "#e1e0d9", "#3a3a37"),
    "pad": ("パッドリング", "#898781", "#6f6e69"),
}
FONT = 'system-ui, -apple-system, "Hiragino Sans", "Noto Sans CJK JP", "Segoe UI", sans-serif'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "documentation", "figures",
                   "gf180", "plan_20261022", "gf180_area_by_function_20261022.svg")


def mid(lo, hi):
    return (lo + hi) / 2


def text_w(s, size):
    """Rough rendered width: CJK about one em, Latin about 0.56 em."""
    return sum(size if ord(c) > 0x2E80 else 0.56 * size for c in s)


def totals():
    lo = sum(i[2] for i in ITEMS)
    hi = sum(i[3] for i in ITEMS)
    by = {f: sum(mid(i[2], i[3]) for i in ITEMS if i[0] == f) for f in FUNCS}
    route = mid(lo * ROUTE[0], hi * ROUTE[1])
    spare = CORE - sum(by.values()) - route
    return lo, hi, by, route, spare


def svg():
    lo, hi, by, route, spare = totals()
    W, X0, X1 = 960, 40, 920
    out = []
    a = out.append
    # ---- die bar: core functions, routing, spare, then the pad ring
    segs = [(FUNCS[f][0], f"var(--{f})", by[f], f) for f in FUNCS]
    segs += [(GRAYS["route"][0], "var(--route)", route, "route"),
             (GRAYS["spare"][0], "var(--spare)", spare, "spare"),
             (GRAYS["pad"][0], "var(--pad)", DIE - CORE, "pad")]
    scale = (X1 - X0 - 2 * (len(segs) - 1)) / DIE
    y_bar, h_bar = 140, 24
    x = X0
    rects, labels = [], []
    for name, color, val, key in segs:
        w = val * scale
        rects.append((x, w, color, name, val, key))
        labels.append((x + w / 2, f"{name} {val:.2f}", f"{100 * val / DIE:.0f} %"))
        x += w + 2
    core_x1 = rects[5][0] + rects[5][1]
    # ---- component bars
    comp = sorted(ITEMS, key=lambda i: -mid(i[2], i[3]))
    y_c0, row = 350, 25
    lab_w = 330
    cx0, cx1 = X0 + lab_w, X1 - 40
    cmax = 1.1
    cs = (cx1 - cx0) / cmax
    H = y_c0 + row * len(comp) + 176
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'font-family=\'{FONT}\' role="img" aria-labelledby="t d">')
    a("<style>")
    a(":root, svg { --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; "
      "--grid:#e1e0d9; --base:#c3c2b7; "
      + " ".join(f"--{k}:{v[1]};" for k, v in FUNCS.items()) + " "
      + " ".join(f"--{k}:{v[1]};" for k, v in GRAYS.items()) + " }")
    a("@media (prefers-color-scheme: dark) { svg { --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; "
      "--muted:#898781; --grid:#2c2c2a; --base:#383835; "
      + " ".join(f"--{k}:{v[2]};" for k, v in FUNCS.items()) + " "
      + " ".join(f"--{k}:{v[2]};" for k, v in GRAYS.items()) + " } }")
    a("text { fill: var(--ink); } .s { fill: var(--ink2); } .m { fill: var(--muted); }")
    a("</style>")
    a('<title id="t">チップ面積の機能別の内訳（2026-10-22 の見積もり）</title>')
    a(f'<desc id="d">ダイ {DIE:.2f} mm2 のうちパッドリングが {DIE - CORE:.2f} mm2。コア {CORE:.2f} mm2 は '
      f'AFE {by["afe"]:.2f}、ADC {by["adc"]:.2f}、支援回路 {by["sup"]:.2f}、デジタル {by["dig"]:.2f}、'
      f'配線 {route:.2f}、予備 {spare:.2f} mm2（中央値）。</desc>')
    a(f'<rect width="{W}" height="{H}" fill="var(--surface)"/>')
    a(f'<text x="{X0}" y="38" font-size="18" font-weight="600">チップ面積の機能別の内訳</text>')
    a(f'<text class="s" x="{X0}" y="60" font-size="12.5">2026-10-22 の見積もり（各項目の下限と上限の中央値）。'
      f'ダイ 3932 × 2531 µm = {DIE:.2f} mm²、コア 3048 × 1647 µm = {CORE:.2f} mm²。</text>')
    a(f'<text class="s" x="{X0}" y="78" font-size="12.5">10/21 の面積見積もりに、10/22 の変更'
      f'（AFE の構成、出力の保持容量、DAC2 の MOS 電流 DAC）を反映。配線とブロック間は +15〜25 %。</text>')
    # die bar section
    a(f'<text x="{X0}" y="106" font-size="13" font-weight="600">ダイ全体（mm²）</text>')
    # brackets over the core and the pad ring
    for x0b, x1b, lab in ((X0, core_x1, f"コア {CORE:.2f} mm²"),
                          (core_x1 + 2, X1, f"パッドリング・四隅・コアまでの隙間 {DIE - CORE:.2f} mm²")):
        a(f'<path d="M{x0b:.1f},{y_bar - 6} V{y_bar - 11} H{x1b:.1f} V{y_bar - 6}" fill="none" '
          f'stroke="var(--base)" stroke-width="1"/>')
        a(f'<text class="s" x="{(x0b + x1b) / 2:.1f}" y="{y_bar - 16}" font-size="11.5" '
          f'text-anchor="middle">{escape(lab)}</text>')
    for x, w, color, name, val, key in rects:
        a(f'<rect x="{x:.1f}" y="{y_bar}" width="{w:.1f}" height="{h_bar}" fill="{color}">'
          f'<title>{escape(name)}: {val:.2f} mm²（ダイの {100 * val / DIE:.1f} %、'
          f'{"コアの " + format(100 * val / CORE, ".1f") + " %" if key != "pad" else "コア外"}）</title></rect>')
    # labels below the bar, greedy rows; a leader line when a label is not right under its segment
    rows_end = []
    for (cx, l1, l2), (x, w, *_rest) in zip(labels, rects):
        tw = max(text_w(l1, 12), text_w(l2, 11)) + 8
        lx = min(max(cx, X0 + tw / 2), X1 - tw / 2)
        r = 0
        while r < len(rows_end) and rows_end[r] > lx - tw / 2:
            r += 1
        if r == len(rows_end):
            rows_end.append(0)
        rows_end[r] = lx + tw / 2
        ty = y_bar + h_bar + 22 + 34 * r
        a(f'<line x1="{cx:.1f}" y1="{y_bar + h_bar + 2}" x2="{lx:.1f}" y2="{ty - 13}" '
          f'stroke="var(--base)" stroke-width="1"/>')
        a(f'<text x="{lx:.1f}" y="{ty}" font-size="12" text-anchor="middle">{escape(l1)}</text>')
        a(f'<text class="m" x="{lx:.1f}" y="{ty + 14}" font-size="11" text-anchor="middle">'
          f'ダイの {escape(l2)}</text>')
    # ---- component chart
    a(f'<text x="{X0}" y="{y_c0 - 52}" font-size="13" font-weight="600">部品ごとの面積（mm²、'
      f'棒は中央値、細線は下限〜上限）</text>')
    lx = X0
    for k, (name, _l, _d) in FUNCS.items():
        a(f'<rect x="{lx}" y="{y_c0 - 38}" width="12" height="12" rx="2" fill="var(--{k})"/>')
        lab = name + {"sup": "（バイアス・クロック・DC サーボ・デカップ）"}.get(k, "")
        a(f'<text class="s" x="{lx + 18}" y="{y_c0 - 28}" font-size="12">{escape(lab)}</text>')
        lx += 18 + text_w(lab, 12) + 22
    # grid and ticks
    y_end = y_c0 + row * len(comp)
    for i in range(0, 12, 2):
        v = i / 10
        gx = cx0 + v * cs
        a(f'<line x1="{gx:.1f}" y1="{y_c0 - 8}" x2="{gx:.1f}" y2="{y_end}" stroke="var(--grid)" stroke-width="1"/>')
        a(f'<text class="m" x="{gx:.1f}" y="{y_end + 16}" font-size="11" text-anchor="middle" '
          f'style="font-variant-numeric: tabular-nums">{v:.1f}</text>')
    a(f'<line x1="{cx0}" y1="{y_c0 - 8}" x2="{cx0}" y2="{y_end}" stroke="var(--base)" stroke-width="1"/>')
    for j, (f, name, l, h) in enumerate(comp):
        y = y_c0 + row * j
        m = mid(l, h)
        bw = max(m * cs, 2.0)
        r = min(4.0, bw / 2)
        bh = 14
        yb = y + (row - bh) / 2 - 4
        a(f'<text x="{cx0 - 10}" y="{yb + 11}" font-size="12" text-anchor="end">{escape(name)}</text>')
        # bar: square at the baseline, 4 px rounded data end
        a(f'<path d="M{cx0:.1f},{yb:.1f} H{cx0 + bw - r:.1f} Q{cx0 + bw:.1f},{yb:.1f} {cx0 + bw:.1f},{yb + r:.1f} '
          f'V{yb + bh - r:.1f} Q{cx0 + bw:.1f},{yb + bh:.1f} {cx0 + bw - r:.1f},{yb + bh:.1f} H{cx0:.1f} Z" '
          f'fill="var(--{f})"><title>{escape(name)}: {m:.3f} mm²（{l:.3f}〜{h:.3f}）</title></path>')
        wy = yb + bh / 2
        a(f'<line x1="{cx0 + l * cs:.1f}" y1="{wy:.1f}" x2="{cx0 + h * cs:.1f}" y2="{wy:.1f}" '
          f'stroke="var(--ink2)" stroke-width="1.5"/>')
        for v in (l, h):
            a(f'<line x1="{cx0 + v * cs:.1f}" y1="{wy - 4:.1f}" x2="{cx0 + v * cs:.1f}" y2="{wy + 4:.1f}" '
              f'stroke="var(--ink2)" stroke-width="1.5"/>')
        a(f'<text class="s" x="{cx0 + max(h, m) * cs + 8:.1f}" y="{yb + 11}" font-size="11.5" '
          f'style="font-variant-numeric: tabular-nums">{m:.2f}</text>')
    # ---- total against the core
    yt = y_end + 52
    blo, bhi = lo * (1 + ROUTE[0]), hi * (1 + ROUTE[1])
    bmid = sum(by.values()) + route
    a(f'<text x="{X0}" y="{yt}" font-size="13" font-weight="600">コアに対する合計（配線込み、mm²）</text>')
    ts = (cx1 - cx0) / 6.0
    yr = yt + 26
    a(f'<text class="s" x="{cx0 - 10}" y="{yr + 4}" font-size="12" text-anchor="end">見積もりの幅と中央値</text>')
    a(f'<line x1="{cx0 + blo * ts:.1f}" y1="{yr:.1f}" x2="{cx0 + bhi * ts:.1f}" y2="{yr:.1f}" '
      f'stroke="var(--ink2)" stroke-width="2" stroke-linecap="round"/>')
    a(f'<circle cx="{cx0 + bmid * ts:.1f}" cy="{yr:.1f}" r="5" fill="var(--ink2)" stroke="var(--surface)" '
      f'stroke-width="2"><title>中央値 {bmid:.2f} mm²（{blo:.2f}〜{bhi:.2f}）</title></circle>')
    a(f'<line x1="{cx0 + CORE * ts:.1f}" y1="{yr - 14:.1f}" x2="{cx0 + CORE * ts:.1f}" y2="{yr + 14:.1f}" '
      f'stroke="var(--ink)" stroke-width="1.5"/>')
    a(f'<text x="{cx0 + CORE * ts:.1f}" y="{yr - 20:.1f}" font-size="11.5" text-anchor="middle">'
      f'コア {CORE:.2f}</text>')
    a(f'<text class="s" x="{cx0 + blo * ts:.1f}" y="{yr + 22:.1f}" font-size="11" text-anchor="middle">{blo:.2f}</text>')
    a(f'<text class="s" x="{cx0 + bmid * ts:.1f}" y="{yr + 22:.1f}" font-size="11" text-anchor="middle">{bmid:.2f}</text>')
    a(f'<text class="s" x="{cx0 + bhi * ts:.1f}" y="{yr + 22:.1f}" font-size="11" text-anchor="middle">{bhi:.2f}</text>')
    a(f'<text x="{cx0 + 3.0 * ts:.1f}" y="{yr + 46:.1f}" font-size="12" text-anchor="middle">'
      f'中央値ならコアに {CORE - bmid:.2f} mm² 残る。上限では {bhi - CORE:.2f} mm² 超える</text>')
    a(f'<text class="m" x="{X0}" y="{H - 14}" font-size="11">生成：gf180/area_by_function.py。'
      f'根拠：gf180_area_estimate_20261021.md、gf180_afe_noise_20261022.md、gf180_quantizer_20261022.md。</text>')
    a("</svg>")
    return "\n".join(out) + "\n", (lo, hi, by, route, spare, blo, bhi, bmid)


def main():
    text, (lo, hi, by, route, spare, blo, bhi, bmid) = svg()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(text)
    print(f"die {DIE:.3f} mm2, core {CORE:.3f}, pad ring {DIE - CORE:.3f}")
    print("| 機能 | 中央値 (mm²) | コアの割合 |")
    print("|---|---|---|")
    for k, (name, _l, _d) in FUNCS.items():
        print(f"| {name} | {by[k]:.2f} | {100 * by[k] / CORE:.0f} % |")
    print(f"| 配線・ブロック間 | {route:.2f} | {100 * route / CORE:.0f} % |")
    print(f"| 予備 | {spare:.2f} | {100 * spare / CORE:.0f} % |")
    print(f"total with routing: {blo:.2f} .. {bhi:.2f} (mid {bmid:.2f}) vs core {CORE:.2f}")
    print(f"wrote {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
