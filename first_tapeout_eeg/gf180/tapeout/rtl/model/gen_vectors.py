"""Generate the stimulus and golden files used by the testbenches.

Usage: python3 gen_vectors.py <build_dir>

Files written to <build_dir>:
  rnd_sat.vec         rounding/saturation vectors: "<din 37b hex> <dout 24b hex>"
  cic_<name>.ops      CIC operation stream (one byte per operation, see cic_golden.py)
  cic_<name>.gold     one line per CIC output strobe: "<data 24b hex> <valid>"
  top_stream.codes    code stream for the top-level test (one byte per frame)
  top_stream.gold     valid CIC outputs of top_stream.codes, one "<data hex>" per line
  vectors.log         coverage summary
"""

import os
import random
import sys

import numpy as np

import cic_golden as g
import sdm2_model as sdm

R = g.R


def write_ops_and_gold(bdir, name, ops, log, min_valid=0):
    ops = bytes(ops)
    with open(os.path.join(bdir, f"cic_{name}.ops"), "wb") as f:
        f.write(ops)
    outs, st = g.cic3_run(ops)
    with open(os.path.join(bdir, f"cic_{name}.gold"), "w") as f:
        for data, valid in outs:
            f.write(f"{data & 0xFFFFFF:06x} {int(valid)}\n")
    nvalid = sum(1 for _, v in outs if v)
    msg = (f"cic_{name}: {len(ops)} ops, {st['inputs']} inputs, {st['clears']} clears "
           f"({st['dropped_by_clear']} inputs dropped by clear), {len(outs)} strobes, "
           f"{nvalid} valid\n  wraps i1/i2/i3 = {st['wrap_i1']}/{st['wrap_i2']}/{st['wrap_i3']}, "
           f"comb1/2/3 = {st['wrap_c1']}/{st['wrap_c2']}/{st['wrap_c3']}\n"
           f"  rounding: ties to even {st['tie_even']}, ties odd->up {st['tie_odd']}, "
           f"up {st['round_up']}, down {st['round_down']}, saturated {st['saturated']}")
    print(msg)
    log.write(msg + "\n")
    if nvalid < min_valid:
        raise SystemExit(f"cic_{name}: only {nvalid} valid outputs (< {min_valid})")
    return outs, st


def gen_rnd_sat(bdir, log):
    rng = random.Random(1234)
    vals = []
    q_list = [0, 1, -1, 2, -2, 3, -3, 1000, -1001, (1 << 22), -(1 << 22) - 1,
              (1 << 23) - 3, (1 << 23) - 2, (1 << 23) - 1, (1 << 23), (1 << 23) + 1,
              -(1 << 23) - 2, -(1 << 23) - 1, -(1 << 23), -(1 << 23) + 1,
              (1 << 24) - 1, -(1 << 24)]
    r_list = [0, 1, 2047, 2048, 2049, 4094, 4095]
    for q in q_list:
        for r in r_list:
            vals.append(q * 4096 + r)
    vals += [-(1 << 36), (1 << 36) - 1]
    for _ in range(20000):
        vals.append(rng.randrange(-(1 << 36), 1 << 36))
    for _ in range(5000):   # values inside the legal CIC output range with ties
        vals.append(rng.randrange(-(1 << 23), 1 << 23) * 4096 + 2048)
    nsat = 0
    with open(os.path.join(bdir, "rnd_sat.vec"), "w") as f:
        for v in vals:
            v = g.wrap(v)
            y = g.round_sat(v)
            nsat += (y != g.round_sat(v, wo=64))
            f.write(f"{v & g.MASK:010x} {y & 0xFFFFFF:06x}\n")
    msg = f"rnd_sat: {len(vals)} vectors, {nsat} saturated"
    print(msg)
    log.write(msg + "\n")


def gen_impulse(bdir, log):
    # baseline x = -1 (c = 15) or x = +1 (c = 16); single-sample impulses of
    # c = 31 / c = 0 placed at several phases of the decimation period
    ops = [15] * 4096
    phases = [0, 1, 2, 3, 511, 512, 1021, 1022, 1023]
    for n, ph in enumerate(phases):
        base = 15 if n % 2 == 0 else 16
        while len(ops) % R != ph:
            ops.append(base)
        ops.append(31 if n % 2 == 0 else 0)
        ops += [base] * 4096
    write_ops_and_gold(bdir, "impulse", ops, log)


def gen_step(bdir, log):
    ops = [0] * (5 * R)          # negative full scale
    ops += [31] * (5 * R)        # step to positive full scale (aligned)
    ops += [16] * (4 * R)        # x = +1
    ops += [15] * (4 * R + 300)  # x = -1, then a step at a non-aligned phase
    ops += [23] * (5 * R)
    ops += [8] * (5 * R + 777)
    write_ops_and_gold(bdir, "step", ops, log)


def gen_stream(bdir, log):
    n_codes = 20_600_000
    codes = sdm.sdm2_codes(n_codes, amp=0.85, freq_hz=37.0, dc=0.05, seed=20261022)
    clear_at = 6_000_321          # plain clear after this many codes
    clear_en_at = 13_000_777      # clear together with the input of this code
    ops = bytearray()
    ops += codes[:clear_at].tobytes()
    ops.append(g.OP_CLEAR)
    ops += codes[clear_at:clear_en_at].tobytes()
    ops.append(g.OP_CLEAR_EN | int(codes[clear_en_at]))
    ops += codes[clear_en_at + 1:].tobytes()
    msg = (f"stream codes: min {codes.min()} max {codes.max()} "
           f"mean x {2.0 * codes.mean() - 31.0:+.4f}")
    print(msg)
    log.write(msg + "\n")
    _, st = write_ops_and_gold(bdir, "stream", ops, log, min_valid=20000)
    for key in ("wrap_i2", "wrap_i3", "wrap_c1", "wrap_c2", "wrap_c3", "tie_even", "tie_odd"):
        if st[key] == 0:
            raise SystemExit(f"cic_stream: coverage item {key} not hit")


def gen_top(bdir, log, n_frames=60000):
    codes = sdm.sdm2_codes(n_frames, amp=0.7, freq_hz=211.0, dc=-0.03, seed=7)
    codes.tofile(os.path.join(bdir, "top_stream.codes"))
    outs, st = g.cic3_run(codes.tobytes())
    valid = [d for d, v in outs if v]
    with open(os.path.join(bdir, "top_stream.gold"), "w") as f:
        for d in valid:
            f.write(f"{d & 0xFFFFFF:06x}\n")
    msg = (f"top_stream: {n_frames} frames, codes {codes.min()}..{codes.max()}, "
           f"{len(valid)} valid outputs, wraps i3 {st['wrap_i3']}")
    print(msg)
    log.write(msg + "\n")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    bdir = sys.argv[1]
    os.makedirs(bdir, exist_ok=True)
    with open(os.path.join(bdir, "vectors.log"), "w") as log:
        gen_rnd_sat(bdir, log)
        gen_impulse(bdir, log)
        gen_step(bdir, log)
        gen_stream(bdir, log)
        gen_top(bdir, log)


if __name__ == "__main__":
    main()
