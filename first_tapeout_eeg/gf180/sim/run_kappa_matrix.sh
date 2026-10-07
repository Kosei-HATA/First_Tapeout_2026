#!/usr/bin/env bash
# Run the int1 kappa-ramp bench for a matrix of (RSET, CC, fs) variants,
# both ramp directions, and extract kappa with fit_kappa.py.
# Usage: run_kappa_matrix.sh   (from gf180/sim)
set -u
TPL=tb_gf180_intsettle_kappa.spice
for fs in 256 512; do
  if [ $fs -eq 256 ]; then TCLK=3.90625u; PH1D=0.1u; PHW=1.62u; PH2D=2.053u; TTOT=78.125u; TM0=58.6u
  else TCLK=1.953125u; PH1D=0.05u; PHW=0.81u; PH2D=1.0265u; TTOT=39.0625u; TM0=29.3u; fi
  for rc in "40k 10p" "25k 10p" "20k 10p" "25k 12p" "25k 15p" "20k 15p"; do
    set -- $rc
    for RAMP in -1 +1; do
      if [ $RAMP = "-1" ]; then VINPV="{VCM+5m}"; VINNV="{VCM-5m}"; VBITV=0; else VINPV="{VCM-5m}"; VINNV="{VCM+5m}"; VBITV="{VDD}"; fi
      sed -e "s/@RSETP@/$1/" -e "s/@CCP@/$2/" -e "s/@TCLK@/$TCLK/g" \
          -e "s/@PH1D@/$PH1D/" -e "s/@PHW@/$PHW/g" -e "s/@PH2D@/$PH2D/" \
          -e "s/@TTOT@/$TTOT/g" -e "s/@TMEAS0@/$TM0/" \
          -e "s|@VINPV@|$VINPV|" -e "s|@VINNV@|$VINNV|" -e "s|@VBITV@|$VBITV|" \
          $TPL > /tmp/tb_kappa_run.spice
      ngspice -b /tmp/tb_kappa_run.spice > /tmp/tb_kappa_run.log 2>&1
      idd=$(grep -o "idd_avg *= *[0-9.e+-]*" /tmp/tb_kappa_run.log | head -1)
      echo "== RSET=$1 CC=$2 fs=${fs}k RAMP=$RAMP  $idd"
      python3 ../results/fit_kappa.py ../results/sdm3_kappa.csv $(python3 -c "print(float('${TCLK%u}')*1e-6)")
      cp ../results/sdm3_kappa.csv "../results/sdm3_kappa_$1_$2_${fs}k_$RAMP.csv"
    done
  done
done
echo ALL DONE
