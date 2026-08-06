#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class SimConfig:
    channels: int = 8
    selected_channel: int = 0
    duration_s: float = 10.0
    fs_mod_hz: int = 16000
    osr: int = 64
    hp_fc_hz: float = 0.5
    lp_fc_hz: float = 30.0
    pga_gain: float = 1000.0
    adc_fs_v: float = 0.05  # differential full scale (±50 mV)
    spi_clk_hz: int = 1_000_000
    frame_bits: int = 24  # 16-bit data + channel/status overhead

    @property
    def fs_out_hz(self) -> int:
        return self.fs_mod_hz // self.osr


def one_pole_highpass(x: np.ndarray, fc_hz: float, fs_hz: float) -> np.ndarray:
    dt = 1.0 / fs_hz
    rc = 1.0 / (2.0 * math.pi * fc_hz)
    alpha = rc / (rc + dt)
    y = np.zeros_like(x)
    x_prev = 0.0
    y_prev = 0.0
    for i, xi in enumerate(x):
        yi = alpha * (y_prev + xi - x_prev)
        y[i] = yi
        x_prev = xi
        y_prev = yi
    return y


def one_pole_lowpass(x: np.ndarray, fc_hz: float, fs_hz: float) -> np.ndarray:
    dt = 1.0 / fs_hz
    rc = 1.0 / (2.0 * math.pi * fc_hz)
    beta = dt / (rc + dt)
    y = np.zeros_like(x)
    y_prev = 0.0
    for i, xi in enumerate(x):
        yi = y_prev + beta * (xi - y_prev)
        y[i] = yi
        y_prev = yi
    return y


def bandpass_0p5_30hz(x: np.ndarray, fs_hz: float, hp_fc_hz: float, lp_fc_hz: float) -> np.ndarray:
    return one_pole_lowpass(one_pole_highpass(x, hp_fc_hz, fs_hz), lp_fc_hz, fs_hz)


def sigma_delta_1bit(x_norm: np.ndarray) -> np.ndarray:
    y = np.empty_like(x_norm)
    integ = 0.0
    q_prev = 0.0
    for i, xi in enumerate(x_norm):
        integ += xi - q_prev
        q = 1.0 if integ >= 0.0 else -1.0
        y[i] = q
        q_prev = q
    return y


def block_average_decimate(x: np.ndarray, osr: int) -> np.ndarray:
    n = len(x) // osr
    return x[: n * osr].reshape(n, osr).mean(axis=1)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def dominant_freq_hz(t: np.ndarray, x: np.ndarray) -> float:
    if len(x) < 8:
        return float("nan")
    dt = float(t[1] - t[0])
    y = x - np.mean(x)
    w = np.hanning(len(y))
    spec = np.fft.rfft(y * w)
    freq = np.fft.rfftfreq(len(y), d=dt)
    amp = np.abs(spec)
    if len(amp) > 0:
        amp[0] = 0.0
    idx = int(np.argmax(amp))
    return float(freq[idx])


def signal_stats(t: np.ndarray, x: np.ndarray) -> dict[str, float]:
    return {
        "rms": rms(x),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
        "dom_freq": dominant_freq_hz(t, x),
    }


def save_block_io_csv(cfg: SimConfig, out_path: Path) -> None:
    rows = [
        {
            "block": "Xtal/PLL",
            "input": "crystal resonance / reference oscillator",
            "output": f"mod_clk={cfg.fs_mod_hz} Hz, spi_clk={cfg.spi_clk_hz} Hz",
            "domain": "clock",
            "note": "low-jitter source for converter and serial timing",
        },
        {
            "block": "PrecisionVoltage",
            "input": "analog supply",
            "output": "stable reference/bias rails",
            "domain": "power/reference",
            "note": f"ADC full scale reference = ±{cfg.adc_fs_v*1e3:.1f} mV",
        },
        {
            "block": "Diff-In + Filter",
            "input": "electrode Vpos/Vneg + common-mode/noise",
            "output": "band-limited differential analog",
            "domain": "analog",
            "note": f"bandpass ~{cfg.hp_fc_hz}-{cfg.lp_fc_hz} Hz",
        },
        {
            "block": "MUX",
            "input": f"{cfg.channels} differential channels",
            "output": f"selected differential channel ch{cfg.selected_channel}",
            "domain": "analog",
            "note": "short routing for multi-channel integration",
        },
        {
            "block": "DiffAmp (PGA)",
            "input": "selected differential analog",
            "output": "gain-scaled analog",
            "domain": "analog",
            "note": f"gain={cfg.pga_gain:.1f}x",
        },
        {
            "block": "SD-ADC + Decimation",
            "input": "PGA analog output",
            "output": f"digital samples @{cfg.fs_out_hz} Hz",
            "domain": "mixed-signal",
            "note": f"1-bit modulator @{cfg.fs_mod_hz} Hz, OSR={cfg.osr}",
        },
        {
            "block": "FIFO Unit",
            "input": "ADC sample words",
            "output": "buffered sample frames",
            "domain": "digital",
            "note": "absorbs burst/jitter mismatch between ADC and SPI",
        },
        {
            "block": "SPI",
            "input": "FIFO frames",
            "output": "serial data stream",
            "domain": "digital I/O",
            "note": f"frame_bits={cfg.frame_bits}, required_rate={cfg.fs_out_hz * cfg.frame_bits} bps",
        },
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["block", "input", "output", "domain", "note"])
        writer.writeheader()
        writer.writerows(rows)


def save_block_io_numeric_csv(
    cfg: SimConfig,
    t: np.ndarray,
    t_out: np.ndarray,
    v_pos_sel: np.ndarray,
    v_neg_sel: np.ndarray,
    raw_diff_sel: np.ndarray,
    filt_diff_sel: np.ndarray,
    mux_out: np.ndarray,
    pga_out: np.ndarray,
    bitstream: np.ndarray,
    adc_out: np.ndarray,
    adc_code: np.ndarray,
    out_path: Path,
) -> None:
    vpos_s = signal_stats(t, v_pos_sel * 1e6)
    vneg_s = signal_stats(t, v_neg_sel * 1e6)
    raw_s = signal_stats(t, raw_diff_sel * 1e6)
    filt_s = signal_stats(t, filt_diff_sel * 1e6)
    pga_s = signal_stats(t, pga_out * 1e3)
    adc_s = signal_stats(t_out, adc_out * 1e6)
    bit_pos_ratio = float(np.mean(bitstream > 0))
    req_bps = cfg.fs_out_hz * cfg.frame_bits
    adc_code_rms = rms(adc_code.astype(np.float64))

    rows = [
        {
            "block": "Xtal/PLL",
            "input_signal": "xtal_ref",
            "input_min": "",
            "input_max": "",
            "input_rms": "",
            "input_unit": "",
            "input_dom_freq_hz": "",
            "output_signal": "mod_clk",
            "output_min": f"{cfg.fs_mod_hz}",
            "output_max": f"{cfg.fs_mod_hz}",
            "output_rms": f"{cfg.fs_mod_hz}",
            "output_unit": "Hz",
            "output_dom_freq_hz": "",
            "note": "converter clock",
        },
        {
            "block": "PrecisionVoltage",
            "input_signal": "analog_supply",
            "input_min": "",
            "input_max": "",
            "input_rms": "",
            "input_unit": "",
            "input_dom_freq_hz": "",
            "output_signal": "adc_full_scale_diff",
            "output_min": f"{-cfg.adc_fs_v*1e3:.3f}",
            "output_max": f"{cfg.adc_fs_v*1e3:.3f}",
            "output_rms": "",
            "output_unit": "mV",
            "output_dom_freq_hz": "",
            "note": "reference range",
        },
        {
            "block": "Diff-In",
            "input_signal": "v_pos_sel",
            "input_min": f"{vpos_s['min']:.3f}",
            "input_max": f"{vpos_s['max']:.3f}",
            "input_rms": f"{vpos_s['rms']:.3f}",
            "input_unit": "uV",
            "input_dom_freq_hz": f"{vpos_s['dom_freq']:.3f}",
            "output_signal": "raw_diff_sel=vpos-vneg",
            "output_min": f"{raw_s['min']:.3f}",
            "output_max": f"{raw_s['max']:.3f}",
            "output_rms": f"{raw_s['rms']:.3f}",
            "output_unit": "uV",
            "output_dom_freq_hz": f"{raw_s['dom_freq']:.3f}",
            "note": f"v_neg_rms={vneg_s['rms']:.3f} uV",
        },
        {
            "block": "Filter (0.5-30Hz)",
            "input_signal": "raw_diff_sel",
            "input_min": f"{raw_s['min']:.3f}",
            "input_max": f"{raw_s['max']:.3f}",
            "input_rms": f"{raw_s['rms']:.3f}",
            "input_unit": "uV",
            "input_dom_freq_hz": f"{raw_s['dom_freq']:.3f}",
            "output_signal": "filtered_diff_sel",
            "output_min": f"{filt_s['min']:.3f}",
            "output_max": f"{filt_s['max']:.3f}",
            "output_rms": f"{filt_s['rms']:.3f}",
            "output_unit": "uV",
            "output_dom_freq_hz": f"{filt_s['dom_freq']:.3f}",
            "note": "band-limited EEG",
        },
        {
            "block": "MUX",
            "input_signal": f"filtered_diff_ch[0..{cfg.channels-1}]",
            "input_min": f"{filt_s['min']:.3f}",
            "input_max": f"{filt_s['max']:.3f}",
            "input_rms": f"{filt_s['rms']:.3f}",
            "input_unit": "uV",
            "input_dom_freq_hz": f"{filt_s['dom_freq']:.3f}",
            "output_signal": f"mux_out_ch{cfg.selected_channel}",
            "output_min": f"{filt_s['min']:.3f}",
            "output_max": f"{filt_s['max']:.3f}",
            "output_rms": f"{filt_s['rms']:.3f}",
            "output_unit": "uV",
            "output_dom_freq_hz": f"{filt_s['dom_freq']:.3f}",
            "note": "selected channel only",
        },
        {
            "block": "DiffAmp (PGA)",
            "input_signal": "mux_out",
            "input_min": f"{filt_s['min']:.3f}",
            "input_max": f"{filt_s['max']:.3f}",
            "input_rms": f"{filt_s['rms']:.3f}",
            "input_unit": "uV",
            "input_dom_freq_hz": f"{filt_s['dom_freq']:.3f}",
            "output_signal": "pga_out",
            "output_min": f"{pga_s['min']:.3f}",
            "output_max": f"{pga_s['max']:.3f}",
            "output_rms": f"{pga_s['rms']:.3f}",
            "output_unit": "mV",
            "output_dom_freq_hz": f"{pga_s['dom_freq']:.3f}",
            "note": f"gain={cfg.pga_gain:.1f}x",
        },
        {
            "block": "SD-ADC + Decimation",
            "input_signal": "pga_out",
            "input_min": f"{pga_s['min']:.3f}",
            "input_max": f"{pga_s['max']:.3f}",
            "input_rms": f"{pga_s['rms']:.3f}",
            "input_unit": "mV",
            "input_dom_freq_hz": f"{pga_s['dom_freq']:.3f}",
            "output_signal": "adc_out",
            "output_min": f"{adc_s['min']:.3f}",
            "output_max": f"{adc_s['max']:.3f}",
            "output_rms": f"{adc_s['rms']:.3f}",
            "output_unit": "uV",
            "output_dom_freq_hz": f"{adc_s['dom_freq']:.3f}",
            "note": f"sd_bit_pos_ratio={bit_pos_ratio:.6f}",
        },
        {
            "block": "FIFO Unit",
            "input_signal": "adc_out_code",
            "input_min": f"{int(np.min(adc_code))}",
            "input_max": f"{int(np.max(adc_code))}",
            "input_rms": f"{adc_code_rms:.3f}",
            "input_unit": "LSB(int16)",
            "input_dom_freq_hz": "",
            "output_signal": "fifo_frame_code",
            "output_min": f"{int(np.min(adc_code))}",
            "output_max": f"{int(np.max(adc_code))}",
            "output_rms": f"{adc_code_rms:.3f}",
            "output_unit": "LSB(int16)",
            "output_dom_freq_hz": "",
            "note": "buffered transfer",
        },
        {
            "block": "SPI",
            "input_signal": "fifo_frame_code",
            "input_min": f"{int(np.min(adc_code))}",
            "input_max": f"{int(np.max(adc_code))}",
            "input_rms": f"{adc_code_rms:.3f}",
            "input_unit": "LSB(int16)",
            "input_dom_freq_hz": "",
            "output_signal": "serial_rate",
            "output_min": f"{req_bps}",
            "output_max": f"{req_bps}",
            "output_rms": f"{req_bps}",
            "output_unit": "bps",
            "output_dom_freq_hz": "",
            "note": f"spi_clk={cfg.spi_clk_hz} Hz",
        },
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "block",
                "input_signal",
                "input_min",
                "input_max",
                "input_rms",
                "input_unit",
                "input_dom_freq_hz",
                "output_signal",
                "output_min",
                "output_max",
                "output_rms",
                "output_unit",
                "output_dom_freq_hz",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def save_block_plot_png(
    t: np.ndarray,
    t_out: np.ndarray,
    v_pos_sel: np.ndarray,
    v_neg_sel: np.ndarray,
    raw_diff: np.ndarray,
    mux_out: np.ndarray,
    pga_out: np.ndarray,
    bitstream: np.ndarray,
    ref_dec: np.ndarray,
    adc_out: np.ndarray,
    out_path: Path,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise ImportError("matplotlib is required to save PNG. Install it in your Python environment.") from e

    sec_main = 2.0
    n_main = min(len(t), int(sec_main * (len(t) / t[-1])))
    sec_bit = 0.02
    n_bit = min(len(t), int(sec_bit * (len(t) / t[-1])))

    fig, axes = plt.subplots(6, 1, figsize=(12, 14), constrained_layout=True)

    axes[0].plot(t[:n_main], v_pos_sel[:n_main] * 1e6, label="Vpos")
    axes[0].plot(t[:n_main], v_neg_sel[:n_main] * 1e6, label="Vneg")
    axes[0].set_title("Diff-In input (selected channel)")
    axes[0].set_ylabel("uV")
    axes[0].legend(loc="upper right")

    axes[1].plot(t[:n_main], raw_diff[:n_main] * 1e6, label="raw diff")
    axes[1].plot(t[:n_main], mux_out[:n_main] * 1e6, label="filtered diff")
    axes[1].set_title("Diff-In + Filter output")
    axes[1].set_ylabel("uV")
    axes[1].legend(loc="upper right")

    axes[2].plot(t[:n_main], mux_out[:n_main] * 1e6, color="tab:green")
    axes[2].set_title("MUX output")
    axes[2].set_ylabel("uV")

    axes[3].plot(t[:n_main], pga_out[:n_main] * 1e3, color="tab:orange")
    axes[3].set_title("DiffAmp (PGA) output")
    axes[3].set_ylabel("mV")

    axes[4].step(t[:n_bit], bitstream[:n_bit], where="post", color="tab:red")
    axes[4].set_title("SD modulator 1-bit stream (20 ms)")
    axes[4].set_ylabel("bit")
    axes[4].set_ylim(-1.2, 1.2)

    axes[5].plot(t_out, ref_dec * 1e6, label="ideal decimated")
    axes[5].plot(t_out, adc_out * 1e6, label="ADC output", alpha=0.8)
    axes[5].set_title("SD-ADC + decimation output")
    axes[5].set_ylabel("uV")
    axes[5].set_xlabel("time [s]")
    axes[5].legend(loc="upper right")

    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def simulate(cfg: SimConfig) -> None:
    if cfg.fs_mod_hz % cfg.osr != 0:
        raise ValueError("fs_mod_hz must be divisible by osr")
    if not (0 <= cfg.selected_channel < cfg.channels):
        raise ValueError("selected_channel is out of range")

    n = int(cfg.duration_s * cfg.fs_mod_hz)
    t = np.arange(n) / cfg.fs_mod_hz
    rng = np.random.default_rng(42)

    eeg_diff = np.zeros((cfg.channels, n))
    for ch in range(cfg.channels):
        a_uv = 12.0 + 4.0 * ch
        f_hz = 8.0 + 0.7 * ch
        eeg_diff[ch] = (
            a_uv * 1e-6 * np.sin(2.0 * math.pi * f_hz * t)
            + 0.35 * a_uv * 1e-6 * np.sin(2.0 * math.pi * (f_hz + 2.0) * t)
            + 8e-6 * np.sin(2.0 * math.pi * 0.2 * t)
        )

    common_mode = 200e-6 * np.sin(2.0 * math.pi * 50.0 * t)
    electrode_noise_sigma = 2e-6
    ep = rng.normal(0.0, electrode_noise_sigma, size=(cfg.channels, n))
    en = rng.normal(0.0, electrode_noise_sigma, size=(cfg.channels, n))
    v_pos = common_mode + eeg_diff / 2.0 + ep
    v_neg = common_mode - eeg_diff / 2.0 + en
    raw_diff = v_pos - v_neg

    diff_filtered = np.zeros_like(eeg_diff)
    for ch in range(cfg.channels):
        vp_f = bandpass_0p5_30hz(v_pos[ch], cfg.fs_mod_hz, cfg.hp_fc_hz, cfg.lp_fc_hz)
        vn_f = bandpass_0p5_30hz(v_neg[ch], cfg.fs_mod_hz, cfg.hp_fc_hz, cfg.lp_fc_hz)
        diff_filtered[ch] = vp_f - vn_f

    mux_out = diff_filtered[cfg.selected_channel]
    pga_out = cfg.pga_gain * mux_out

    x_norm = np.clip(pga_out / cfg.adc_fs_v, -0.999, 0.999)
    bitstream = sigma_delta_1bit(x_norm)
    dec_norm = block_average_decimate(bitstream, cfg.osr)
    adc_out = dec_norm * cfg.adc_fs_v

    ref_dec = block_average_decimate(x_norm, cfg.osr) * cfg.adc_fs_v
    err = adc_out - ref_dec
    snr_db = 20.0 * np.log10(rms(ref_dec) / max(rms(err), 1e-15))

    out_n = len(adc_out)
    t_out = np.arange(out_n) / cfg.fs_out_hz
    clean_out = block_average_decimate(
        cfg.pga_gain * eeg_diff[cfg.selected_channel], cfg.osr
    )

    req_bps = cfg.fs_out_hz * cfg.frame_bits
    spi_margin = cfg.spi_clk_hz / max(req_bps, 1)
    adc_code = np.clip(np.round((adc_out / cfg.adc_fs_v) * 32767.0), -32768, 32767).astype(np.int16)

    print("=== Module I/O assumptions ===")
    print("Diff-In+Filter: (Vpos, Vneg) -> band-limited differential analog (0.5-30 Hz)")
    print("MUX: [ch0..chN-1] differential analog -> selected channel differential analog")
    print("DiffAmp(PGA): selected differential analog -> gain-scaled analog")
    print("SD-ADC(+decimation): analog -> digital samples @ fs_out")
    print("FIFO Unit: digital samples -> burst-tolerant buffered frames")
    print("SPI: buffered frames -> serialized digital stream")
    print("Xtal/PLL: reference clock -> modulator/spi clocks")
    print("PrecisionVoltage: supply/reference -> stable bias/ref rails")

    print("\n=== Key simulation results ===")
    print(f"channels={cfg.channels}, selected_channel={cfg.selected_channel}")
    print(f"fs_mod={cfg.fs_mod_hz} Hz, OSR={cfg.osr}, fs_out={cfg.fs_out_hz} Hz")
    print(f"PGA gain={cfg.pga_gain:.1f}x, ADC full-scale=±{cfg.adc_fs_v*1e3:.1f} mV")
    print(f"SNR (ref vs ADC output) = {snr_db:.2f} dB")
    print(f"SPI required data rate = {req_bps} bps")
    print(f"SPI margin (clk/required) = {spi_margin:.1f}x")
    base = Path(".")
    block_io_path = base / "block_io_spec.csv"
    block_io_numeric_path = base / "block_io_numeric_spec.csv"
    mod_csv_path = base / "block_waveforms_mod.csv"
    out_csv_path = base / "block_waveforms_out.csv"
    png_path = base / "block_waveforms.png"

    save_block_io_csv(cfg, block_io_path)

    np.savetxt(
        mod_csv_path,
        np.column_stack(
            [
                t,
                v_pos[cfg.selected_channel] * 1e6,
                v_neg[cfg.selected_channel] * 1e6,
                raw_diff[cfg.selected_channel] * 1e6,
                mux_out * 1e6,
                pga_out * 1e3,
                bitstream,
            ]
        ),
        delimiter=",",
        header="time_s,v_pos_uV,v_neg_uV,raw_diff_uV,filtered_mux_out_uV,pga_out_mV,sd_bit",
        comments="",
    )

    np.savetxt(
        out_csv_path,
        np.column_stack([t_out, clean_out * 1e6, ref_dec * 1e6, adc_out * 1e6, err * 1e6, adc_code]),
        delimiter=",",
        header="time_s,clean_after_pga_uV,ideal_decimated_uV,adc_out_uV,error_uV,fifo_spi_code_int16",
        comments="",
    )

    save_block_io_numeric_csv(
        cfg=cfg,
        t=t,
        t_out=t_out,
        v_pos_sel=v_pos[cfg.selected_channel],
        v_neg_sel=v_neg[cfg.selected_channel],
        raw_diff_sel=raw_diff[cfg.selected_channel],
        filt_diff_sel=diff_filtered[cfg.selected_channel],
        mux_out=mux_out,
        pga_out=pga_out,
        bitstream=bitstream,
        adc_out=adc_out,
        adc_code=adc_code,
        out_path=block_io_numeric_path,
    )

    save_block_plot_png(
        t=t,
        t_out=t_out,
        v_pos_sel=v_pos[cfg.selected_channel],
        v_neg_sel=v_neg[cfg.selected_channel],
        raw_diff=raw_diff[cfg.selected_channel],
        mux_out=mux_out,
        pga_out=pga_out,
        bitstream=bitstream,
        ref_dec=ref_dec,
        adc_out=adc_out,
        out_path=png_path,
    )
    print(f"saved: {block_io_path}")
    print(f"saved: {block_io_numeric_path}")
    print(f"saved: {mod_csv_path}")
    print(f"saved: {out_csv_path}")
    print(f"saved: {png_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Behavioral simulation for EEG-focused SoC block chain")
    parser.add_argument("--channels", type=int, default=8)
    parser.add_argument("--selected-channel", type=int, default=0)
    parser.add_argument("--duration", type=float, default=10.0, help="seconds")
    parser.add_argument("--fs-mod", type=int, default=16000, help="modulator sampling rate [Hz]")
    parser.add_argument("--osr", type=int, default=64, help="oversampling ratio")
    parser.add_argument("--pga-gain", type=float, default=1000.0, help="PGA gain")
    parser.add_argument("--adc-fs-mv", type=float, default=50.0, help="ADC full-scale [mV] (differential)")
    args = parser.parse_args()

    simulate(
        SimConfig(
            channels=args.channels,
            selected_channel=args.selected_channel,
            duration_s=args.duration,
            fs_mod_hz=args.fs_mod,
            osr=args.osr,
            pga_gain=args.pga_gain,
            adc_fs_v=args.adc_fs_mv * 1e-3,
        )
    )
