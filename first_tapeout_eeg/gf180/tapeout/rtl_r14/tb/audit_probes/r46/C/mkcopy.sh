#!/bin/zsh
# usage: mkcopy.sh <dir>   -- a fresh copy of c7fff346's rtl, rtl_r14 and documents, with the external inputs linked
set -e
D=$1
REPO=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg
rm -rf $D; mkdir -p $D; cd $D
git -C $REPO archive c7fff346 gf180/tapeout/rtl gf180/tapeout/rtl_r14 documentation/gf180_digital_control_requirements_20261119.md documentation/gf180_digital_control_spec_20261119.md documentation/gf180_digital_control_audit_20261120.md | tar -x
mkdir -p gf180/tapeout/rtl/build/e2e
ln -s $REPO/gf180/tapeout/rtl/build/e2e/s4.codes $REPO/gf180/tapeout/rtl/build/e2e/s20.codes gf180/tapeout/rtl/build/e2e/
for R in typical_ov2.5V_150u_then_dc-39mV_300u typical_ov2.5V_50u_rec60u_f20k_a0.28; do
  mkdir -p gf180/tapeout/pex/runs/adc_overload_r12/$R
  ln -s $REPO/gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv
done
# a runner that stops at the first failed group (same groups and commands; tb_spi_r14 and outputs before the long benches)
cd gf180/tapeout/rtl_r14
python3 - <<'PY'
s = open("run_tests_r14.sh").read()
old = '''        RES+=("FAIL  $name  (build/$name.log)")
    fi
}'''
new = '''        RES+=("FAIL  $name  (build/$name.log)")
        printf '%s\\n' "${RES[@]}"; echo "STOPPED at the first failed group"; exit 1
    fi
}'''
assert s.count(old) == 1
s = s.replace(old, new)
old2 = '''        RES+=("FAIL  $name  (time limit $lim s; build/$name.log)")
        return'''
new2 = '''        RES+=("FAIL  $name  (time limit $lim s; build/$name.log)")
        printf '%s\\n' "${RES[@]}"; echo "STOPPED at the first failed group"; exit 1'''
assert s.count(old2) == 1
s = s.replace(old2, new2)
order_old = '''run tb_top_r14 5400 top_t
run tb_spi_r14 3600 spi_t
run tb_top_r14_fifo4 5400 top4_t
run outputs 1200 outputs_t'''
order_new = '''run tb_spi_r14 3600 spi_t
run outputs 1200 outputs_t
run tb_top_r14 5400 top_t
run tb_top_r14_fifo4 5400 top4_t'''
assert s.count(order_old) == 1
s = s.replace(order_old, order_new)
open("run_tests_stopfirst.sh", "w").write(s)
PY
chmod +x run_tests_stopfirst.sh
echo "copy ready: $D"
