"""audit 44, auditor C: edits of the hand-drawn lanes of wave.py's startup, APPLY and frame diagrams, each through
wave.check() and wave.selftest() (the selftest's own mutations are unaffected by these lanes). Run from the spec dir."""
import io, contextlib, os, sys
sys.path.insert(0, os.getcwd())
import wave as W
orig = {"apply": W.apply_seq, "startup": W.startup, "frame": W.frame}
def patched(which, edit):
    f0 = orig[which]
    def f():
        d = f0()
        for ln in d["signal"]:
            if isinstance(ln, dict) and ln.get("name") in edit:
                ln.update(edit[ln["name"]])
        return d
    return f
cases = [
 ("apply: FIFO emptied at RECOVER's entry instead of the APPLY's tick (SEQ-05)", "apply", {"FIFO": {"wave": "=.....=.....=..."}}),
 ("apply: active settings change at RECOVER's entry instead of PRE's", "apply", {"アクティブの設定": {"wave": "=.....=........."}}),
 ("apply: DRDY_N pulses during PRE and PULSE (DAT-01: stores only in FILL->RUN and RUN)", "apply", {"DRDY_N（パルス）": {"wave": "01.0101........."}}),
 ("startup: FIFO emptied at RUN, not at START's tick", "startup", {"FIFO": {"wave": "=..........==..", "data": ["", "空（START の tick）", "格納"]}}),
 ("startup: DRDY_N pulses from FILL's entry", "startup", {"DRDY_N（パルス）": {"wave": "1........0101.."}}),
 ("startup: CIC valid from ALIGN", "startup", {"CIC": {"wave": "x......=.=.....", "data": ["クリア後の充填", "有効"]}}),
 ("frame: CIC input at cycle 4", "frame", {"ADC：CIC の入力": {"wave": W.levels(33, {5})}}),
 ("frame: CHOP_BLANK 3 cycles (BLANK 2) under the caption of 15", "frame", {"縁のフレーム：CHOP_BLANK（15）": {"wave": W.levels(33, {0, 1, 2})}}),
]
for name, which, edit in cases:
    W.apply_seq, W.startup, W.frame = orig["apply"], orig["startup"], orig["frame"]
    if which == "apply": W.apply_seq = patched("apply", edit)
    if which == "startup": W.startup = patched("startup", edit)
    if which == "frame": W.frame = patched("frame", edit)
    changed = (W.apply_seq() != orig["apply"]()) or (W.startup() != orig["startup"]()) or (W.frame() != orig["frame"]())
    errs = W.check()
    with contextlib.redirect_stdout(io.StringIO()) as so:
        rc = W.selftest()
    print(f"{'PASSES' if not errs else 'caught'} check, selftest rc {rc}, lane changed {changed} :: {name}" + (f" [{errs[0][:80]}]" if errs else ""))
