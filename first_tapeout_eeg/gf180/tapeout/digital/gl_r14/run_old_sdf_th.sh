#!/bin/zsh
# Diagnostic (11/25): why the gate level with delays (SDF) of the two digital macros of the 13th chip (eeg_digital_top f2,
# eeg_adc_dig f3; tb/gl_shadow.sv) failed in tb_top and in the end-to-end slice at max_ss and nom_tt on 11/20
# (rtl/build/logs/top_dlc2_gl_sdf_*.log, rtl/build/e2e/s4_0of200_gl_sdf_*.log) and passed at min_ff.
#
# rtl/tb/tb_top.sv drives the quantizer outputs TH with the code of a frame only from 1.5 to 2.5 MCLK after the
# CMP_STROBE edge e0 (random bits otherwise), so that a capture at a wrong edge shows in the RTL. On the chip TH is
# launched by e0 and settles a few ns after it; eeg_adc_dig's constraints (digital/eeg_adc_dig/*.sdc) take it 15 ns after
# e0 and give the logic from TH to the capture flip-flops (popcount, thermometer, DWA rotation) two MCLK periods, up to e2.
# With the SDF that logic is slower than the 15.3 ns the bench leaves before e2 at the slow corners. This runs the same
# bench, gate level with the SDF, twice per corner for the first 2 ms: as it is (orig) and with TH = therm(c) from 15 ns
# after e0 to 15 ns after the next e0 (th15), the timing the STA signs off. Nothing in rtl/ is written: the bench is
# copied, and the SDF and the cell models prepared by rtl/gl_sdf_prep.sh on 11/19 (rtl/build/gl_sdf) are read.
#
# usage: run_old_sdf_th.sh   (from a Terminal panel tab; about half an hour, 4 runs side by side on the efficiency cores)
# out:   gf180/tapeout/digital/eeg_digital_top_r14/runs/sys_diag_old_sdf_20261125/{<variant>_<corner>.log,summary.txt}
set -u
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
R=$T/rtl
RUN=$T/digital/eeg_digital_top_r14/runs/sys_diag_old_sdf_20261125
SCL=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref
G=$R/build/gl_sdf
mkdir -p $RUN/build
cp $R/build/top_stream.codes $R/build/top_stream.gold $RUN/build/ || exit 1
sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' $T/layout/gds/eeg_digital_top.nl.v > $RUN/eeg_digital_top_gl.v
sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' $T/layout/gds/eeg_adc_dig.nl.v > $RUN/eeg_adc_dig_gl.v
shasum -a 256 $T/layout/gds/eeg_digital_top.nl.v $T/layout/gds/eeg_adc_dig.nl.v $G/*.sdf $G/cells_*.v > $RUN/inputs.sha256
# orig: the bench as it is, stopped at 2 ms; th15: TH = therm(c) 15 ns after the CMP_STROBE edge, held to 15 ns after
# the next one
perl -pe 's/^module tb_top;$/module tb_top;\n    initial begin #(2.0e6); \$display("diagnostic: stopped at 2 ms"); \$finish; end/' \
    $R/tb/tb_top.sv > $RUN/tb_top_orig.sv
grep -q 'diagnostic: stopped at 2 ms' $RUN/tb_top_orig.sv || { echo "module line of tb_top.sv not found"; exit 1; }
perl -0777 -pe 's/        TH = \$random\(seed\);\n        #\(1\.5 \* TMCLK\);\n        TH = therm\(c\);[^\n]*\n        #\(1\.0 \* TMCLK\);\n        TH = \$random\(seed\);\n/        #(15.0);\n        TH = therm(c);                         \/\/ diagnostic: 15 ns after e0, held until 15 ns after the next e0\n/' \
    $RUN/tb_top_orig.sv > $RUN/tb_top_th15.sv
if cmp -s $RUN/tb_top_orig.sv $RUN/tb_top_th15.sv || ! grep -q 'diagnostic: 15 ns after e0' $RUN/tb_top_th15.sv; then
    echo "the TH block of tb_top.sv was not found"; exit 1
fi
diff $R/tb/tb_top.sv $RUN/tb_top_th15.sv > $RUN/tb_top_th15.diff
RTL=(eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv eeg_fifo.sv eeg_regs.sv
     eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv eeg_adc_dig.sv eeg_digital_sys.sv)
RTL=(${RTL/#/$R/})
CELLS=($SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $G/cells_9t.v
       $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $G/cells_7t.v)
cd $RUN || exit 1
date
for c in max_ss_125C_3v00 nom_tt_025C_3v30; do
    case $c in max_*) t=max ;; min_*) t=min ;; *) t=typ ;; esac
    for v in orig th15; do
        ( iverilog -g2012 -I $R/tb -gspecify -ginterconnect -T$t -DGL_SDF \
              -DGL_SDF_TOP=\"$G/eeg_digital_top_gl__$c.sdf\" -DGL_SDF_ADC=\"$G/eeg_adc_dig_gl__$c.sdf\" -DTB=tb_top \
              -Ptb_top.DLC=2 -Ptb_top.NSAMP=40 -s tb_top -s gl_shadow -o build/${v}_$c.vvp \
              $RTL $RUN/tb_top_$v.sv $R/tb/gl_shadow.sv $CELLS $RUN/eeg_digital_top_gl.v $RUN/eeg_adc_dig_gl.v \
              > ${v}_$c.log 2>&1 &&
          vvp -n build/${v}_$c.vvp >> ${v}_$c.log 2>&1
          echo "exit $?" >> ${v}_$c.log ) &
    done
done
wait
date
for f in orig_max_ss_125C_3v00 th15_max_ss_125C_3v00 orig_nom_tt_025C_3v30 th15_nom_tt_025C_3v30; do
    echo "$f: $(grep -E '^(PASS|FAIL): gate level' $f.log)  first: $(grep -m1 'GL MISMATCH' $f.log)"
done | tee $RUN/summary.txt
