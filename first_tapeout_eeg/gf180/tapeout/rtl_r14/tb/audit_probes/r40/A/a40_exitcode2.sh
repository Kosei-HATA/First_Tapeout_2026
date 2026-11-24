#!/usr/bin/env bash
# run_tests_r14.sh's verdict line under its own `set -o pipefail`: when grep -q exits on the FAIL line before printf
# has written the rest, printf dies of SIGPIPE (141), pipefail makes the pipeline non-zero and `!` turns it into 0
set -u
set -o pipefail
declare -a RES
RES+=("FAIL  tb_x  (build/tb_x.log)")
for i in $(seq 1 ${1:-16}); do RES+=("PASS  group_$i  1 s"); done
! printf '%s\n' "${RES[@]}" | grep -q FAIL
