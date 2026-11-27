#!/usr/bin/env python3
"""tb_e2e_r15's samples against the golden CIC (rtl/model/cic_golden.py): VER-04 (11/28).

The bench gives the stream's bytes one per frame from the RESET_N release (position start + i for CIC input i; it
checks that every input is its frame's code) and logs 'C s n_in' for the armed clear (ALIGN) at the output with SEQ s
and 'S seq data status' for every sample read. As in check_top_r14.py, output SEQ s closes the inputs [s R, (s + 1) R),
and a clear at the output s restarts the filter from the input (s + 1) R. Every sample must equal the golden output
with its SEQ bit for bit and be valid; SEQ runs +1 from sample to sample, the count equals the bench's.

usage: check_e2e_r15.py <codes file> <bench log>
       check_e2e_r15.py --selftest <codes file> <bench log>   (each of 7 errors written into a copy of the log must
                                                              fail the check; the log itself must pass)
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "model"))
import cic_golden as G  # noqa: E402

R = 1024


def check(codes_path, log_path, quiet=False):
    out = sys.stdout
    if quiet:
        sys.stdout = open(os.devnull, "w")
    try:
        return main_check(codes_path, log_path)
    finally:
        if quiet:
            sys.stdout.close()
            sys.stdout = out


def selftest(codes_path, log_path):
    lines = open(log_path).read().split("\n")
    s_idx = [k for k, ln in enumerate(lines) if ln.startswith("S ")]
    c_idx = [k for k, ln in enumerate(lines) if ln.startswith("C ")]
    h_idx = [k for k, ln in enumerate(lines) if ln.startswith("# ")]
    mid = s_idx[len(s_idx) // 2]

    def flip(ln, bit):
        f = ln.split()
        f[2] = f"{int(f[2], 16) ^ (1 << bit):06x}"
        return " ".join(f)

    def field(ln, k, delta):
        f = ln.split()
        f[k] = str(int(f[k]) + delta)
        return " ".join(f)

    def start_plus_one(ln):
        f = ln.split()
        k = f.index("start")
        f[k + 1] = str(int(f[k + 1]) + 1)
        return " ".join(f)

    muts = [
        ("a sample's DATA LSB flipped", lambda L: L.__setitem__(mid, flip(L[mid], 0))),
        ("a sample's DATA MSB flipped", lambda L: L.__setitem__(mid, flip(L[mid], 23))),
        ("two samples swapped", lambda L: (L.__setitem__(mid, lines[mid + 1]), L.__setitem__(mid + 1, lines[mid]))),
        ("a sample dropped", lambda L: L.__setitem__(mid, "")),
        ("the clear one output later", lambda L: L.__setitem__(c_idx[0], field(L[c_idx[0]], 1, 1))),
        ("the stream one frame later", lambda L: L.__setitem__(h_idx[0], start_plus_one(L[h_idx[0]]))),
        ("a status byte with OVERRUN", lambda L: L.__setitem__(mid, L[mid][:-2] + "c0")),
    ]
    n_det = 0
    ok = check(codes_path, log_path, quiet=True) == 0
    print(f"the log itself: {'passes' if ok else 'FAILS'}")
    for name, mut in muts:
        L = list(lines)
        mut(L)
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as t:
            t.write("\n".join(L))
        rc = check(codes_path, t.name, quiet=True)
        os.unlink(t.name)
        n_det += rc != 0
        print(f"  {'detected' if rc != 0 else 'MISSED  '} {name}")
    print(f"{n_det} of {len(muts)} errors detected")
    return 0 if ok and n_det == len(muts) else 1


def main_check(codes_path, log_path):
    stream = open(codes_path, "rb").read()
    n = len(stream)
    head, clears, samples, end = None, [], [], None
    for line in open(log_path):
        f = line.split()
        if not f:
            continue
        if f[0] == "#":
            head = dict(zip(f[2::2], f[3::2]))
        elif f[0] == "C":
            clears.append((int(f[1]), int(f[2])))
        elif f[0] == "S":
            samples.append((int(f[1]), int(f[2], 16), int(f[3], 16)))
        elif f[0] == "E":
            end = dict(zip(f[1::2], (int(x) for x in f[2::2])))
    fails = []
    if head is None or end is None:
        print("FAIL: the bench log has no header or no end line (the bench stopped early)")
        return 1
    start = int(head["start"])
    if int(head["nstream"]) != n:
        fails.append(f"the bench's stream has {head['nstream']} bytes, {codes_path} {n}")
    if len(clears) != 1:
        fails.append(f"{len(clears)} armed clears, expected 1")
    if not samples:
        fails.append("no samples")
    if fails:
        print("FAIL: " + "; ".join(fails))
        return 1
    s_c, n_in_c = clears[0]
    i0 = (s_c + 1) * R                       # the first input after the clear
    # the clear's output closes the inputs up to (s_c + 1) R; the input count logged at its strobe is that or a few
    # more (inputs taken between the R-th input and the strobe, 4 MCLK later: none, one input per frame)
    if not (i0 <= n_in_c <= i0 + 1):
        fails.append(f"the clear at SEQ {s_c} logged {n_in_c} inputs, expected {i0}")
    seqs = [s for s, _, _ in samples]
    gaps = [k for k in range(1, len(seqs)) if seqs[k] != (seqs[k - 1] + 1) % 65536]
    if gaps:
        fails.append(f"SEQ breaks after sample {gaps[0] - 1} ({seqs[gaps[0] - 1]} -> {seqs[gaps[0]]})")
    if len(samples) != end["samples"]:
        fails.append(f"{len(samples)} samples logged, the bench read {end['samples']}")
    last = max(seqs)
    if last >= 65536 - 1:
        fails.append("SEQ wrapped (the check assumes fewer than 65,535 outputs)")
    ninp = (last - s_c) * R                  # inputs from the clear to the last sample's output
    pos0 = start + i0
    wrapped = (pos0 % n) + ninp > n
    codes = [stream[(pos0 + j) % n] for j in range(ninp)]
    bad = [c for c in codes if c > 31]
    if bad:
        fails.append(f"{len(bad)} stream bytes above 31")
    out, st = G.cic3_run(codes)
    mism, invalid, shown = 0, 0, 0
    for s, d, status in samples:
        j = s - (s_c + 1)
        if j < 0 or j >= len(out):
            fails.append(f"sample SEQ {s} outside the golden outputs {s_c + 1}..{s_c + len(out)}")
            break
        gd, gv = out[j]
        dv = d - (1 << 24) if d & (1 << 23) else d
        if not gv:
            invalid += 1
        if dv != gd or not gv:
            mism += 1
            if shown < 10:
                shown += 1
                print(f"  SEQ {s}: data {dv} (0x{d:06x}), golden {gd} valid {gv}")
    nst = sum(1 for _, _, status in samples if status != 0x80)
    if nst:
        fails.append(f"{nst} status bytes other than VALID alone (0x80)")
    if invalid:
        fails.append(f"{invalid} samples of outputs the golden model marks invalid (the filter settling)")
    if mism:
        fails.append(f"{mism} of {len(samples)} samples differ from the golden CIC")
    vals = [gd for gd, gv in out[seqs[0] - (s_c + 1):]]
    print(f"{len(samples)} samples, SEQ {seqs[0]}..{last}; the armed clear at SEQ {s_c} (input {i0}, stream position "
          f"{pos0 % n}); {ninp} inputs from the clear{' (the stream wrapped)' if wrapped else ''}; golden coverage: "
          f"wraps i1/i2/i3 {st['wrap_i1']}/{st['wrap_i2']}/{st['wrap_i3']}, comb {st['wrap_c1']}/{st['wrap_c2']}/"
          f"{st['wrap_c3']}, rounding ties even/odd {st['tie_even']}/{st['tie_odd']}, saturated {st['saturated']}; "
          f"sample range {min(vals)}..{max(vals)} LSB")
    if fails:
        print("FAIL: " + "; ".join(fails))
        return 1
    print(f"PASS: every sample bit-exact with the golden CIC ({len(samples)} samples)")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2], sys.argv[3]))
    sys.exit(main_check(sys.argv[1], sys.argv[2]))
