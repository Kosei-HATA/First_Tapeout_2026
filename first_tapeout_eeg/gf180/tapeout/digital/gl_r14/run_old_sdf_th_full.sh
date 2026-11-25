#!/bin/zsh
# The 13th chip's two digital macros (eeg_digital_top f2, eeg_adc_dig f3; the r12 / r13 chips) at gate level with the SDF,
# in full, with the quantizer outputs TH driven as on the chip (11/25). run_old_sdf_th.sh showed that the failures of
# 11/20 at max_ss and nom_tt (tb_top, the end-to-end slice s4:0/200) come from the testbenches' TH, valid only from 1.5 to
# 2.5 MCLK after the CMP_STROBE edge: with TH = therm(c) from 15 ns after e0 to 15 ns after the next e0 (the input delay of
# eeg_adc_dig's constraints) the first 2 ms match at both corners. This runs both testbenches that way to their end at
# max_ss and nom_tt (min_ff passed on 11/20 as they are): rtl/tb/tb_top.sv (DLC 2, 40 samples) and rtl/tb/tb_e2e.sv with
# the slice rtl/build/e2e/s4_0of200.{codes,gold} (21 samples, as run_e2e.sh --gl s4:0/200 ran it). Nothing in rtl/ is
# written: the benches are copied, the SDF and cell models of 11/19 (rtl/build/gl_sdf) and the slice are read.
#
# usage: run_old_sdf_th_full.sh   (from a Terminal panel tab; about 6 hours on the efficiency cores, 4 runs side by side)
# out:   gf180/tapeout/digital/eeg_digital_top_r14/runs/sys_diag_old_sdf_full_20261125/{<bench>_<corner>.log,summary.txt}
set -u
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
R=$T/rtl
RUN=$T/digital/eeg_digital_top_r14/runs/sys_diag_old_sdf_full_20261125
SCL=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref
G=$R/build/gl_sdf
mkdir -p $RUN/build
cp $R/build/top_stream.codes $R/build/top_stream.gold $R/build/e2e/s4_0of200.codes $R/build/e2e/s4_0of200.gold $RUN/build/ || exit 1
sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' $T/layout/gds/eeg_digital_top.nl.v > $RUN/eeg_digital_top_gl.v
sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' $T/layout/gds/eeg_adc_dig.nl.v > $RUN/eeg_adc_dig_gl.v
shasum -a 256 $T/layout/gds/eeg_digital_top.nl.v $T/layout/gds/eeg_adc_dig.nl.v $G/*.sdf $G/cells_*.v $RUN/build/* > $RUN/inputs.sha256
for b in tb_top tb_e2e; do
    perl -0777 -pe 's/        TH = \$random\(seed\);\n        #\(1\.5 \* TMCLK\);\n        TH = therm\(c\);[^\n]*\n        #\(1\.0 \* TMCLK\);\n        TH = \$random\(seed\);\n/        #(15.0);\n        TH = therm(c);                         \/\/ 11\/25: 15 ns after e0, held until 15 ns after the next e0\n/' \
        $R/tb/$b.sv > $RUN/${b}_th15.sv
    grep -q '11/25: 15 ns after e0' $RUN/${b}_th15.sv || { echo "the TH block of $b.sv was not found"; exit 1; }
    diff $R/tb/$b.sv $RUN/${b}_th15.sv > $RUN/${b}_th15.diff
done
RTL=(eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv eeg_fifo.sv eeg_regs.sv
     eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv eeg_adc_dig.sv eeg_digital_sys.sv)
RTL=(${RTL/#/$R/})
CELLS=($SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $G/cells_9t.v
       $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $G/cells_7t.v)
cd $RUN || exit 1
date
for c in max_ss_125C_3v00 nom_tt_025C_3v30; do
    case $c in max_*) t=max ;; min_*) t=min ;; *) t=typ ;; esac
    flags=(-g2012 -I $R/tb -gspecify -ginterconnect -T$t -DGL_SDF -DGL_SDF_TOP=\"$G/eeg_digital_top_gl__$c.sdf\"
           -DGL_SDF_ADC=\"$G/eeg_adc_dig_gl__$c.sdf\")
    ( t0=$SECONDS
      iverilog $flags -DTB=tb_top -Ptb_top.DLC=2 -Ptb_top.NSAMP=40 -s tb_top -s gl_shadow -o build/tb_top_$c.vvp \
          $RTL $RUN/tb_top_th15.sv $R/tb/gl_shadow.sv $CELLS $RUN/eeg_digital_top_gl.v $RUN/eeg_adc_dig_gl.v > tb_top_$c.log 2>&1 &&
      vvp -n build/tb_top_$c.vvp >> tb_top_$c.log 2>&1
      echo "exit $?, $((SECONDS - t0)) s" >> tb_top_$c.log ) &
    ( t0=$SECONDS
      iverilog $flags -DTB=tb_e2e -s tb_e2e -s gl_shadow -o build/tb_e2e_$c.vvp \
          $RTL $RUN/tb_e2e_th15.sv $R/tb/gl_shadow.sv $CELLS $RUN/eeg_digital_top_gl.v $RUN/eeg_adc_dig_gl.v > tb_e2e_$c.log 2>&1 &&
      vvp -n build/tb_e2e_$c.vvp +codes=build/s4_0of200.codes +gold=build/s4_0of200.gold +nsamp=21 \
          +out=build/s4_0of200_$c.samples >> tb_e2e_$c.log 2>&1
      echo "exit $?, $((SECONDS - t0)) s" >> tb_e2e_$c.log ) &
done
wait
date
for f in tb_top_max_ss_125C_3v00 tb_top_nom_tt_025C_3v30 tb_e2e_max_ss_125C_3v00 tb_e2e_nom_tt_025C_3v30; do
    echo "$f: $(grep -E '^(PASS|FAIL)' $f.log | tr '\n' ' ')$(grep -m1 'GL MISMATCH' $f.log)  $(tail -n 1 $f.log)"
done | tee $RUN/summary.txt
