#!/bin/zsh
# The end-to-end slice of the 13th chip's two digital macros at gate level with the SDF, TH driven as on the chip (11/26):
# run_old_sdf_th_full.sh again for rtl/tb/tb_e2e.sv alone, with the TH block replaced so that the bench's own SEL check
# keeps its time. tb_e2e.sv checks SEL in the same per-frame block, after the 2.5 MCLK of its TH sequence and a further
# (DLC + 1 - 2.5) MCLK + 1 ns (1 ns after the SEL update edge e3); run_old_sdf_th_full.sh shortened the 2.5 MCLK to the
# 15 ns of the new TH launch, so its check ran 60 ns early and saw every frame's previous SEL (23,684 errors of the bench at
# both corners, while the gate level matched the RTL in all 757,898 cycles and the 21 samples matched). Here TH = therm(c)
# from 15 ns after e0, and the block then waits the rest of the 2.5 MCLK. tb_top.sv checks SEL in a block of its own and
# was right as run there. Nothing in rtl/ is written.
#
# usage: run_old_sdf_e2e_th.sh   (from a Terminal panel tab; about 4 hours on the efficiency cores, 2 runs side by side)
# out:   gf180/tapeout/digital/eeg_digital_top_r14/runs/sys_diag_old_sdf_e2e_20261126/{tb_e2e_<corner>.log,summary.txt}
set -u
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
R=$T/rtl
RUN=$T/digital/eeg_digital_top_r14/runs/sys_diag_old_sdf_e2e_20261126
SCL=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref
G=$R/build/gl_sdf
mkdir -p $RUN/build
cp $R/build/e2e/s4_0of200.codes $R/build/e2e/s4_0of200.gold $RUN/build/ || exit 1
sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' $T/layout/gds/eeg_digital_top.nl.v > $RUN/eeg_digital_top_gl.v
sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' $T/layout/gds/eeg_adc_dig.nl.v > $RUN/eeg_adc_dig_gl.v
shasum -a 256 $T/layout/gds/eeg_digital_top.nl.v $T/layout/gds/eeg_adc_dig.nl.v $G/*.sdf $G/cells_*.v $RUN/build/* > $RUN/inputs.sha256
perl -0777 -pe 's/        TH = \$random\(seed\);\n        #\(1\.5 \* TMCLK\);\n        TH = therm\(c\);[^\n]*\n        #\(1\.0 \* TMCLK\);\n        TH = \$random\(seed\);\n/        #(15.0);\n        TH = therm(c);                         \/\/ 11\/26: 15 ns after e0, held until 15 ns after the next e0\n        #(2.5 * TMCLK - 15.0);                 \/\/ the rest of the 2.5 MCLK: the SEL check below keeps its time\n/' \
    $R/tb/tb_e2e.sv > $RUN/tb_e2e_th15.sv
grep -q '11/26: 15 ns after e0' $RUN/tb_e2e_th15.sv || { echo "the TH block of tb_e2e.sv was not found"; exit 1; }
diff $R/tb/tb_e2e.sv $RUN/tb_e2e_th15.sv > $RUN/tb_e2e_th15.diff
RTL=(eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv eeg_fifo.sv eeg_regs.sv
     eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv eeg_adc_dig.sv eeg_digital_sys.sv)
RTL=(${RTL/#/$R/})
CELLS=($SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $G/cells_9t.v
       $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $G/cells_7t.v)
cd $RUN || exit 1
date
for c in max_ss_125C_3v00 nom_tt_025C_3v30; do
    case $c in max_*) t=max ;; min_*) t=min ;; *) t=typ ;; esac
    ( t0=$SECONDS
      iverilog -g2012 -I $R/tb -gspecify -ginterconnect -T$t -DGL_SDF -DGL_SDF_TOP=\"$G/eeg_digital_top_gl__$c.sdf\" \
          -DGL_SDF_ADC=\"$G/eeg_adc_dig_gl__$c.sdf\" -DTB=tb_e2e -s tb_e2e -s gl_shadow -o build/tb_e2e_$c.vvp \
          $RTL $RUN/tb_e2e_th15.sv $R/tb/gl_shadow.sv $CELLS $RUN/eeg_digital_top_gl.v $RUN/eeg_adc_dig_gl.v > tb_e2e_$c.log 2>&1 &&
      vvp -n build/tb_e2e_$c.vvp +codes=build/s4_0of200.codes +gold=build/s4_0of200.gold +nsamp=21 \
          +out=build/s4_0of200_$c.samples >> tb_e2e_$c.log 2>&1
      echo "exit $?, $((SECONDS - t0)) s" >> tb_e2e_$c.log ) &
done
wait
date
for f in tb_e2e_max_ss_125C_3v00 tb_e2e_nom_tt_025C_3v30; do
    echo "$f: $(grep -E '^(PASS|FAIL)' $f.log | tr '\n' ' ')$(grep -m1 -E 'GL MISMATCH|^ERROR' $f.log)  $(tail -n 1 $f.log)"
done | tee $RUN/summary.txt
