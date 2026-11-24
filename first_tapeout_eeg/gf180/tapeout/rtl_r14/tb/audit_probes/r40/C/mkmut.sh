#!/bin/zsh
# audit40 C: make mutant copy a40c/mut/<name> from a40c/pristine, link inputs, apply edits from tools/muts.py,
# write an early-exit runner run_mut.sh (spec group skipped: it reads no RTL); optional 2nd arg: group order list
set -e
S=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad
B=$S/a40c
R=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg
name=$1
D=$B/mut/$name
rm -rf $D
mkdir -p $D
cp -R $B/pristine/gf180 $B/pristine/documentation $D/
mkdir -p $D/gf180/tapeout/rtl/build/e2e
ln -s $R/gf180/tapeout/rtl/build/e2e/s4.codes $R/gf180/tapeout/rtl/build/e2e/s20.codes $D/gf180/tapeout/rtl/build/e2e/
for X in typical_ov2.5V_150u_then_dc-39mV_300u typical_ov2.5V_50u_rec60u_f20k_a0.28; do
  mkdir -p $D/gf180/tapeout/pex/runs/adc_overload_r12/$X
  ln -s $R/gf180/tapeout/pex/runs/adc_overload_r12/$X/out.csv $D/gf180/tapeout/pex/runs/adc_overload_r12/$X/out.csv
done
$R/gf180/tools/venv310/bin/python $B/tools/apply_mut.py $name $D
S2=$D/gf180/tapeout/rtl_r14/run_tests_r14.sh
sed -e 's/^run spec 1800 spec$/: # spec group skipped (reads no RTL)/' \
    -e 's/^\(run [a-z_0-9]* [0-9]* [a-z_0-9]*\)$/\1; if printf "%s\\n" "${RES[@]}" | grep -q FAIL; then printf "%s\\n" "${RES[@]}"; echo "EARLY EXIT: DETECTED"; exit 1; fi/' \
    $S2 > $D/gf180/tapeout/rtl_r14/run_mut.sh
chmod +x $D/gf180/tapeout/rtl_r14/run_mut.sh
grep -c "EARLY EXIT" $D/gf180/tapeout/rtl_r14/run_mut.sh
echo $D
