#!/bin/zsh
# The waveform capture of the r15 macro with the SDF of 3 corners (11/28; wave_sim_r15.py compares it with the spec's
# timing diagrams): gl_sdf_r15.sv with GL_WAVE_VCD, in lockstep with the RTL as run_gl_r15.sh runs it, writes the pins
# of the RTL and of the netlist (and the RTL's frame cycle) from RUN for 40 frames, the LATEST read, a sample read and 40
# frames, then ends. Uses the run folder of run_gl_r15.sh (its archived sources, netlist, register names and the SDF
# copies of its sdf step).
# usage: run_wave_r15.sh <macro run tag>     (from a Terminal panel tab; about 20 min)
# out:   gf180/tapeout/digital/eeg_digital_top_r15/runs/gl_<tag>/wave/<corner>.{vcd,log}
set -u
TAG=$1
ROOT=/Users/noah/Codings/First_Tapeout_2026
T=$ROOT/first_tapeout_eeg/gf180/tapeout
HERE=$T/digital/gl_r15
RUN=$T/digital/eeg_digital_top_r15/runs/gl_$TAG
SCL=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/verilog
SRC=$RUN/src/first_tapeout_eeg/gf180/tapeout
for f in $RUN/gl_names.svh $RUN/eeg_digital_top_gl.v $RUN/sdf/cells_9t.v; do
    [ -f $f ] || { echo "$f missing: run run_gl_r15.sh $TAG <commit> prep, and its sdf step"; exit 1; }
done
shasum -a 256 -c $RUN/netlist.sha256 > /dev/null || { echo "FAIL: the netlist changed since prep"; exit 1; }
mkdir -p $RUN/wave
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv)
cd $SRC/rtl_r15 || exit 1
date
for c in max_ss_125C_3v00 nom_tt_025C_3v30 min_ff_n40C_3v60; do
    case $c in max_*) t=max ;; min_*) t=min ;; *) t=typ ;; esac
    ( t0=$SECONDS
      rm -f build/wave_$c.vvp
      { iverilog -g2012 -I spec -I tb -I build -I $RUN -gspecify -ginterconnect -T$t -DGL_SDF \
            "-DGL_SDF_FILE=\"$RUN/sdf/$c.sdf\"" "-DGL_WAVE_VCD=\"$RUN/wave/$c.vcd\"" -DTB=gl_sdf_r15 \
            -s gl_sdf_r15 -s gl_shadow_r15 -o build/wave_$c.vvp $RTL $HERE/gl_sdf_r15.sv $SCL/primitives.v \
            $RUN/sdf/cells_9t.v $HERE/gl_shadow_r15.sv $RUN/eeg_digital_top_gl.v > $RUN/wave/$c.comp.log 2>&1 &&
        rm -f build/wave_$c.vvp.stale && vvp -n build/wave_$c.vvp
        echo "exit $?"; } > $RUN/wave/$c.log 2>&1
      echo "wave capture with the SDF of $c: $((SECONDS - t0)) s" >> $RUN/wave/$c.log ) &
done
wait
date
grep -h "^PASS\|^FAIL\|GL MISMATCH" $RUN/wave/*.log
echo WAVE_R15_DONE
