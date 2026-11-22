#!/bin/zsh
# mkmut.sh <tag>: a fresh copy of rtl and rtl_r14 (no build/) from the clean audit copy, inputs linked read-only
S=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad
C=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg
T=${1:?tag}
D=$S/audit31_C_work/mut/$T
rm -rf $D; mkdir -p $D/gf180/tapeout
rsync -a --exclude build --exclude __pycache__ $S/audit31_C/gf180/tapeout/rtl $S/audit31_C/gf180/tapeout/rtl_r14 $D/gf180/tapeout/
mkdir -p $D/gf180/tapeout/rtl/build/e2e
ln -s $C/gf180/tapeout/rtl/build/e2e/s4.codes $C/gf180/tapeout/rtl/build/e2e/s20.codes $D/gf180/tapeout/rtl/build/e2e/
for R in typical_ov2.5V_150u_then_dc-39mV_300u typical_ov2.5V_50u_rec60u_f20k_a0.28; do
  mkdir -p $D/gf180/tapeout/pex/runs/adc_overload_r12/$R
  ln -s $C/gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv $D/gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv
done
# the docs the spec group's fresh checks read
mkdir -p $D/documentation && cp $S/audit31_C/documentation/*.md $D/documentation/
echo $D
