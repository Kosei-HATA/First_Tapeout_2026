#!/bin/zsh
# The complete mutation run on one committed version, in its own copy (audit round 24, auditor C: from round 8 on every
# complete run was stopped before the next round's fixes, so none had finished since round 7). The copy is a git archive
# of the version under gf180/tapeout/rtl_r14/build/fullrun_<version>/ (git-ignored), with the inputs outside version
# control linked read-only; nothing edits it, so the run ends on its own. Run from a Terminal panel tab:
#   gf180/tapeout/rtl_r14/run_fullmut_r14.sh <version>
# The record is build/fullrun_<version>/gf180/tapeout/rtl_r14/build/mutate_<date>-<pid>.log.
H=${1:?usage: run_fullmut_r14.sh <version>}
C=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg
PY=$C/gf180/tools/venv310/bin/python
H=$(git -C $C rev-parse --short "$H") || exit 1
D=$C/gf180/tapeout/rtl_r14/build/fullrun_$H
rm -rf $D && mkdir -p $D && cd $D || exit 1
git -C $C archive $H gf180/tapeout/rtl gf180/tapeout/rtl_r14 documentation/gf180_digital_control_spec_20261119.md \
    documentation/gf180_digital_control_requirements_20261119.md | tar -x || exit 1
mkdir -p gf180/tapeout/rtl/build/e2e
ln -s $C/gf180/tapeout/rtl/build/e2e/s4.codes $C/gf180/tapeout/rtl/build/e2e/s20.codes gf180/tapeout/rtl/build/e2e/
for R in typical_ov2.5V_150u_then_dc-39mV_300u typical_ov2.5V_50u_rec60u_f20k_a0.28; do
    mkdir -p gf180/tapeout/pex/runs/adc_overload_r12/$R
    ln -s $C/gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv
done
cd gf180/tapeout/rtl_r14 || exit 1
# the version, for the record (audit round 25, auditor C: this copy lies inside the checkout, so git run here answers
# for the checkout; the runner compares every file of the copy with this version at the start and the end)
print -r -- "$(git -C $C rev-parse "$H") $C" > FULLRUN_VERSION || exit 1
date "+the complete mutation run of $H: start %Y-%m-%d %H:%M:%S"
$PY tb/mutate_top_r14.py -j 3
echo "mutate_top_r14.py rc $?"
date "+end %Y-%m-%d %H:%M:%S"
