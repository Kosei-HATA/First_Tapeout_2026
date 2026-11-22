#!/bin/zsh
# hangcheck.sh <mutant name>: a copy with the deletion mutant; tb_tick, tb_clkgen (600 s limit) and tb_chop1 as
# run_tests_r14.sh builds them, then tb_top_r14 (killed at its first ERROR) - what the runner's unit_benches sees first
S=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/audit28_C
P=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
$P $S/tools/mkmut.py $S/tools/del_mutants.py $1 > /dev/null || exit 1
cd $S/mut/$1/gf180/tapeout/rtl_r14 || exit 1
mkdir -p build; cp $S/mut/w0/gf180/tapeout/rtl_r14/build/{top_r14.codes,reg_tests.svh,pin_tests.svh} build/ 2>/dev/null || cp $S/gf180/tapeout/rtl_r14/build/{top_r14.codes,reg_tests.svh,pin_tests.svh} build/
IV="iverilog -g2012 -I ../rtl/spec -I tb -I build"
${=IV} -o build/tt.vvp eeg_clkgen.sv tb/tb_tick.sv 2>/dev/null && print -r -- "tb_tick: $(timeout 600 vvp -n build/tt.vvp | grep -E '^PASS|^FAIL|^ERROR' | head -2 | tr '\n' ' ')"
${=IV} -o build/tc.vvp eeg_clkgen.sv ../rtl/tb/tb_clkgen.sv 2>/dev/null
t0=$SECONDS; out=$(timeout 600 vvp -n build/tc.vvp | grep -E '^PASS|^FAIL|^ERROR' | head -2 | tr '\n' ' '); rc=$?
print -r -- "tb_clkgen: ${out:-no closing line} ($((SECONDS - t0)) s)"
$P $S/tools/screen.py $S/mut/$1 top | cut -c1-200
