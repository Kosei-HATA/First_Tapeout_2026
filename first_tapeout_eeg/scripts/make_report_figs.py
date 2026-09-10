#!/usr/bin/env python3
"""Generate measured-vs-ideal comparison figures for the 20260902 EEG AFE SoC.
All numbers are measured this week (2026-09-04/05) via LS-fit / device-sum noise /
coherent FFT of bitstreams. Sources are cited per figure."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

plt.rcParams["font.family"] = ["Hiragino Sans", "Arial", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.expanduser("~/Codings/First_Tapeout_2026/first_tapeout_eeg")
RES = os.path.join(ROOT, "source/trials/20260902/results")
OUT = os.path.join(ROOT, "documentation/figures/20260905")
os.makedirs(OUT, exist_ok=True)

C_MEAS = "#0072B2"   # measured (blue)
C_IDEAL = "#D55E00"  # ideal (vermillion)
C_OLD = "#999999"    # legacy 8 kHz (gray)
C_PASS = "#009E73"
C_FAIL = "#CC79A7"

# ---------------------------------------------------------------- fig 1: AFE freq response
# LS-fit amplitudes (mV) for 100 uV-side (200 uV diff) input; gain = amp/0.2mV
f_new = [0.5, 1, 4, 8, 40]                       # f_chop = 1 kHz (current design)
a_new = [3.4599, 5.0499, 6.2474, 6.3363, 6.3657]
f_old = [1, 4, 8, 40, 100]                       # f_chop = 8 kHz (previous design)
a_old = [1.0098, 3.4367, 5.0073, 6.2566, 6.3189]
g_new = [a/0.2 for a in a_new]; g_old = [a/0.2 for a in a_old]

fig, ax = plt.subplots(figsize=(7, 4.2))
ax.axhline(32, color=C_IDEAL, lw=1.5, ls="--", label="理想 (×32 フラット)")
ax.axhspan(30.4, 33.6, color=C_IDEAL, alpha=0.10, label="理想 ±5 %")
ax.axvspan(0.5, 100, color="0.9", alpha=0.4)
ax.text(1.6, 11, "目標帯域 0.5-100 Hz", fontsize=8, color="0.35")
ax.plot(f_old, g_old, "s--", color=C_OLD, label="旧設計 (f_chop=8 kHz)")
ax.plot(f_new, g_new, "o-", color=C_MEAS, lw=2, label="現設計 (f_chop=1 kHz)")
for f, g in zip(f_new, g_new):
    ax.annotate(f"{g:.1f}", (f, g), textcoords="offset points", xytext=(0, 7),
                fontsize=8, ha="center", color=C_MEAS)
ax.set_xscale("log"); ax.set_xlabel("信号周波数 [Hz]"); ax.set_ylabel("PGA ゲイン [V/V]")
ax.set_ylim(0, 38); ax.set_xlim(0.4, 130)
ax.set_title("AFE (チョップ PGA ×32) 周波数応答: 実測 vs 理想")
ax.legend(loc="lower right", fontsize=9); ax.grid(True, which="both", alpha=0.25)
fig.tight_layout(); fig.savefig(f"{OUT}/01_afe_freq_response.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------- fig 2: PVT corners
corners = ["TT\n1.80V 27℃", "SS\n1.62V 125℃", "FF\n1.98V −40℃", "SF\n1.80V 27℃", "FS\n1.80V 27℃"]
gains = [31.68, 31.47, 31.77, 31.70, 31.66]
idds  = [70.9, 63.3, 98.6, 78.1, 64.6]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.8))
bars = ax1.bar(corners, gains, color=C_MEAS, width=0.6)
ax1.axhline(32, color=C_IDEAL, ls="--", lw=1.5, label="理想 32")
ax1.axhspan(30.4, 33.6, color=C_IDEAL, alpha=0.10)
for b, g in zip(bars, gains):
    ax1.annotate(f"{g:.2f}", (b.get_x()+b.get_width()/2, g), ha="center",
                 xytext=(0, 4), textcoords="offset points", fontsize=9)
ax1.set_ylim(28, 34); ax1.set_ylabel("ゲイン [V/V] @8 Hz")
ax1.set_title("PVT 5 コーナー: ゲイン (全て PASS)"); ax1.grid(axis="y", alpha=0.25)
ax1.legend(fontsize=8)
bars2 = ax2.bar(corners, idds, color="#56B4E9", width=0.6)
for b, i in zip(bars2, idds):
    ax2.annotate(f"{i:.1f}", (b.get_x()+b.get_width()/2, i), ha="center",
                 xytext=(0, 4), textcoords="offset points", fontsize=9)
ax2.set_ylabel("消費電流 idd [µA]"); ax2.set_title("PVT 5 コーナー: 消費電流")
ax2.grid(axis="y", alpha=0.25)
fig.tight_layout(); fig.savefig(f"{OUT}/02_afe_pvt.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------- fig 3: noise
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.8), gridspec_kw={"width_ratios": [1, 1.4]})
ax1.bar(["実測 (0.5-100 Hz)", "規格上限"], [0.38, 1.0], color=[C_MEAS, "0.7"], width=0.55)
ax1.set_ylabel("入力換算雑音 [µVrms]"); ax1.set_title("帯域内雑音 (P0)")
for i, v in enumerate([0.38, 1.0]):
    ax1.annotate(f"{v:.2f}", (i, v), ha="center", xytext=(0, 4),
                 textcoords="offset points", fontsize=10)
ax1.grid(axis="y", alpha=0.25)
# dominant device contributions to output noise (measured per-device onoise, RSS)
fnoi = [10, 100, 1000, 8000, 50000]
rss  = [9877.3, 3975.8, 1228.7, 170.1, 76.7]   # nV/rtHz at PGA output
ax2.plot(fnoi, rss, "o-", color=C_MEAS, lw=2, label="出力雑音 RSS (支配: 段2 1/f)")
ax2.axvline(1000, color=C_IDEAL, ls="--", lw=1)
ax2.annotate("f_chop=1 kHz\n(復調で帯域内へ畳まれるのはこの点)", (1000, 1228),
             textcoords="offset points", xytext=(-78, 30), fontsize=8, color=C_IDEAL)
ax2.set_xscale("log"); ax2.set_yscale("log")
ax2.set_xlabel("周波数 [Hz]"); ax2.set_ylabel("出力雑音密度 [nV/√Hz]")
ax2.set_title("デバイス別雑音実測 (ngspice onoise 合算)")
ax2.legend(fontsize=8); ax2.grid(True, which="both", alpha=0.25)
fig.tight_layout(); fig.savefig(f"{OUT}/03_afe_noise.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------- fig 4: ADC spectrum
def bitstream_fft(path, fs=16e3, skip=0.0):
    d = np.loadtxt(path); t = d[:, 0]; bit = d[:, -1]
    n = np.arange(1, int(t.max()*fs)-1); ts = n/fs - 1e-6
    b = (np.interp(ts, t, bit) > 0.9).astype(float)*2 - 1
    if skip > 0:
        b = b[int(skip*fs):]
    Nc = (len(b)//500)*500
    b = b[:Nc]
    X = np.fft.rfft(b*np.hanning(Nc))/Nc*2/np.mean(np.hanning(Nc))
    fr = np.fft.rfftfreq(Nc, 1/fs)
    return fr, np.abs(X)

fr, Xa = bitstream_fft(f"{RES}/sdm1ct_cap.csv")
fig, ax = plt.subplots(figsize=(7.5, 4.2))
ax.plot(fr, 20*np.log10(Xa+1e-9), color=C_MEAS, lw=0.7)
ax.axvline(32, color=C_IDEAL, ls="--", lw=1.2)
ax.annotate("入力信号 32 Hz (0.6 FS)", (32, 20*np.log10(0.6)), xytext=(60, -12),
            textcoords="offset points", fontsize=9, color=C_IDEAL,
            arrowprops=dict(arrowstyle="->", color=C_IDEAL))
ax.axvspan(0.5, 100, color="0.88", alpha=0.5)
ax.text(1.0, -8, "EEG 帯域", fontsize=8, color="0.35")
ax.set_xscale("log"); ax.set_xlim(0.5, 8000)
ax.set_xlabel("周波数 [Hz]"); ax.set_ylabel("ビットストリーム振幅 [dBFS]")
ax.set_title("CT ΣΔ ADC (1 次・16 kHz): 出力スペクトル実測\n"
             "帯域内 SNDR = 47.9 dB (1 次 OSR=64 の理論天井 ~52 dB)")
ax.grid(True, which="both", alpha=0.25)
fig.tight_layout(); fig.savefig(f"{OUT}/04_adc_spectrum.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------- fig 5: E2E
fr2, X2 = bitstream_fft(f"{RES}/e2e_1s.csv", skip=0.6*1.024)
y = np.loadtxt(os.path.join(ROOT, "source/trials/20260902/verilog/cic_out.txt"))
tout = np.arange(len(y))/250.0
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
ax1.plot(fr2, 20*np.log10(X2+1e-9), color=C_MEAS, lw=0.8)
ax1.axvline(8, color=C_PASS, ls="--", lw=1.2)
ax1.annotate("EEG 8 Hz: 0.122 FS (期待 0.128)", (8, 20*np.log10(0.122)),
             xytext=(12, -25), textcoords="offset points", fontsize=9, color=C_PASS,
             arrowprops=dict(arrowstyle="->", color=C_PASS))
ax1.axvline(50, color=C_OLD, ls=":", lw=1.2)
ax1.annotate("50 Hz 同相: 0.0008 FS", (50, 20*np.log10(0.0009)), xytext=(12, 18),
             textcoords="offset points", fontsize=9, color="0.35",
             arrowprops=dict(arrowstyle="->", color="0.5"))
ax1.set_xscale("log"); ax1.set_xlim(0.5, 300)
ax1.set_xlabel("周波数 [Hz]"); ax1.set_ylabel("[dBFS]")
ax1.set_title("E2E ビットストリーム (電極 ±300 mV オフセット下)")
ax1.grid(True, which="both", alpha=0.25)
sel = (tout >= 0.7)
ax2.plot(tout[sel], y[sel]/16384, color=C_MEAS, lw=1.2)
ax2.set_xlabel("時間 [s]"); ax2.set_ylabel("CIC 出力 [FS]")
ax2.set_title("CIC デシメータ RTL 出力 (iverilog 実検証)\n8 Hz が復元 (0.120 FS、期待比 −2 %)")
ax2.grid(True, alpha=0.25)
fig.tight_layout(); fig.savefig(f"{OUT}/05_e2e_chain.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------- fig 6: Monte Carlo
fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
ax = axes[0]
ax.bar(["実測平均"], [abs(-0.49)], color=C_MEAS, width=0.5,
       yerr=[[0.206],[0.206]], capsize=5, label="平均 ∓ σ")
ax.axhline(5.0, color=C_IDEAL, ls="--", lw=1.3, label="許容 5 %")
ax.set_ylabel("ゲイン誤差 [%]"); ax.set_title("ゲイン誤差 (P1)")
ax.set_ylim(0, 6); ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.25)
ax = axes[1]
ax.bar(["最小", "平均"], [71.5, 84.0], color=C_MEAS, width=0.5)
ax.axhline(70, color=C_IDEAL, ls="--", lw=1.3, label="許容下限 70 dB (MC)")
ax.set_ylabel("CMRR@200 Hz [dB]"); ax.set_title("CMRR (P0)")
ax.set_ylim(60, 95); ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.25)
ax = axes[2]
ax.bar(["平均", "σ"], [45.35, 109.76], color=["#56B4E9", C_MEAS], width=0.5)
ax.set_ylabel("残留オフセット [µV]"); ax.set_title("残留オフセット\n(固有 HP が出力 DC を抑圧)")
ax.grid(axis="y", alpha=0.25)
fig.suptitle("Monte Carlo N=30 (入力対オフセット σ=0.5 mV + Cf 比 σ=0.3 %)", fontsize=10)
fig.tight_layout(rect=[0, 0, 1, 0.93]); fig.savefig(f"{OUT}/06_monte_carlo.png", dpi=160); plt.close(fig)

# ---------------------------------------------------------------- fig 7: acceptance dashboard
items = [
    ("入力換算雑音 0.5-100 Hz", "≤1.0 µVrms", "0.38 µVrms", 0.38, 1.0, True, "P0"),
    ("CMRR (MC 最小)", "≥70 dB", "71.5 dB", 71.5, 70, True, "P0"),
    ("ゲイン誤差 @8 Hz (PVT 最悪)", "≤5 %", "1.63 %", 1.63, 5.0, True, "P1"),
    ("入力インピーダンス @10 Hz", "≥100 MΩ", "~500 MΩ (容量支配)", 500, 100, True, "P1"),
    ("電極オフセット ±300 mV", "非飽和", "E2E: 飽和なし", 1, 1, True, "P0"),
    ("SNDR (帯域内, ADC)", "1 次天井 ~52 dB", "47.9 dB", 47.9, 52, True, "参考"),
    ("ゲイン平坦性 0.5-2 Hz", "フラット", "−46 % @0.5 Hz (既知)", 0, 1, False, "次期課題"),
]
fig, ax = plt.subplots(figsize=(8.5, 4.6))
ypos = np.arange(len(items))[::-1]
for y, (name, target, meas, val, ref, ok, pr) in zip(ypos, items):
    color = C_PASS if ok else C_FAIL
    ax.barh(y, 1.0, color=color, alpha=0.25, height=0.62)
    ax.text(0.02, y, f"{name}   [{pr}]", va="center", fontsize=9, fontweight="bold")
    ax.text(0.98, y, f"目標 {target} ／ 実測 {meas}", va="center", ha="right", fontsize=9)
ax.set_yticks([]); ax.set_xticks([])
ax.set_xlim(0, 1); ax.set_ylim(-0.6, len(items)-0.4)
ax.set_title("受入基準ダッシュボード (test6 acceptance criteria との照合、2026-09-05 時点)")
for s in ax.spines.values():
    s.set_visible(False)
fig.tight_layout(); fig.savefig(f"{OUT}/07_acceptance_dashboard.png", dpi=160); plt.close(fig)

print("figures written to", OUT)
for f in sorted(os.listdir(OUT)):
    print(" ", f)
