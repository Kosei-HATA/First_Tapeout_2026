# gl_sdf_prep.sh - sourced by run_tests.sh and run_e2e.sh when GL_SDF_CORNER is set (11/19):
# the gate-level runs with delays (tb/gl_shadow.sv, +define+GL_SDF).
#
# In: GL_SDF_CORNER (a LibreLane STA corner: max_ss_125C_3v00, nom_tt_025C_3v30, min_ff_n40C_3v60, ...),
#     SCL (the PDK's libs.ref), GL_SDF_TOP_RUN / GL_SDF_ADC_RUN (the macro runs in ../digital/*/runs/;
#     default f2_rerun_20261119 / f3_rerun_20261119, the re-runs of f2 / f3 whose netlists, DEF and SDF
#     are those of the chip: gf180/tapeout/digital/README_rerun_20261119.md).
# Out: GL_DEFS (iverilog flags), GL_CELLS (the cell models), GL_TAG (default sdf_<corner>).
#
# Two things Icarus Verilog 13 needs:
#   - The netlists' modules are renamed *_gl (the RTL has the same names), so the copies of the SDF in
#     build/gl_sdf/ name the design's CELLTYPE the same way.
#   - The PDK's cell models write the select path of mux2 and the inputs of xor2 / xnor2 (108 paths in each
#     library) as "ifnone (posedge S => (Z:S))" plus the negedge twin, which Icarus drops ("sorry: ifnone
#     with an edge-sensitive path is not supported"): those arcs would have no delay at all, and the SDF's
#     "(IOPATH S Z ...)" would match nothing. build/gl_sdf/cells_{7t,9t}.v are copies of the models with
#     each such pair written as one plain path "(S => Z)", which the SDF's IOPATH then sets (of the two
#     IOPATH entries of the arc, the second one written). The scan flip-flops keep 24 ifnone edge paths of
#     their own (not used in these netlists). Everything else of the models is unchanged.
# Timing checks: Icarus does not run them ("Timing checks are not supported", "TIMINGCHECK not
# supported"); setup / hold are the STA's (documentation/gf180_digital_verification_20261024.md).

GL_SDF_TOP_SRC=../digital/eeg_digital_top/runs/${GL_SDF_TOP_RUN:-f2_rerun_20261119}/final/sdf/$GL_SDF_CORNER/eeg_digital_top__$GL_SDF_CORNER.sdf
GL_SDF_ADC_SRC=../digital/eeg_adc_dig/runs/${GL_SDF_ADC_RUN:-f3_rerun_20261119}/final/sdf/$GL_SDF_CORNER/eeg_adc_dig__$GL_SDF_CORNER.sdf
for f in "$GL_SDF_TOP_SRC" "$GL_SDF_ADC_SRC"; do
    [ -s "$f" ] || { echo "no SDF: $f"; exit 1; }
done
mkdir -p build/gl_sdf
GL_SDF_TOP=build/gl_sdf/eeg_digital_top_gl__$GL_SDF_CORNER.sdf
GL_SDF_ADC=build/gl_sdf/eeg_adc_dig_gl__$GL_SDF_CORNER.sdf
sed 's/(CELLTYPE "eeg_digital_top")/(CELLTYPE "eeg_digital_top_gl")/' "$GL_SDF_TOP_SRC" > "$GL_SDF_TOP"
sed 's/(CELLTYPE "eeg_adc_dig")/(CELLTYPE "eeg_adc_dig_gl")/' "$GL_SDF_ADC_SRC" > "$GL_SDF_ADC"
for t in 7t 9t; do
    src=$SCL/gf180mcu_fd_sc_mcu${t}5v0/verilog/gf180mcu_fd_sc_mcu${t}5v0.v
    # written once (corners running side by side read the same copies)
    [ -s build/gl_sdf/cells_$t.v ] && [ build/gl_sdf/cells_$t.v -nt "$src" ] && [ build/gl_sdf/cells_$t.v -nt gl_sdf_prep.sh ] && continue
    perl -0777 -pe 's/ifnone[ \t]*\n((?:[ \t]*\/\/[^\n]*\n)?)([ \t]*)\(posedge (\w+) => \((\w+):\w+\)\) = (\([^)]*\));/$1$2($3 => $4) = $5;/g;
                    s/ifnone[ \t]*\n(?:[ \t]*\/\/[^\n]*\n)?[ \t]*\(negedge \w+ => \(\w+:\w+\)\) = \([^)]*\);[ \t]*\n//g' \
        "$src" > build/gl_sdf/cells_$t.v
done
GL_CELLS="$SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v build/gl_sdf/cells_9t.v
          $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v build/gl_sdf/cells_7t.v"
case $GL_SDF_CORNER in max_*) GL_T=max ;; min_*) GL_T=min ;; *) GL_T=typ ;; esac
GL_DEFS="-gspecify -ginterconnect -T$GL_T -DGL_SDF -DGL_SDF_TOP=\"$GL_SDF_TOP\" -DGL_SDF_ADC=\"$GL_SDF_ADC\""
GL_TAG=${GL_TAG:-sdf_$GL_SDF_CORNER}
