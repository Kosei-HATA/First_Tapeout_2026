#!/bin/bash
set -e
ROOT=/work/Test-2-4/manufacturing_preflight/analog/ngspice48_isolated
cd "$ROOT"
date -u +%FT%TZ > build_started.txt
cd source
./autogen.sh > ../autogen.log 2>&1
cd ..
mkdir -p build install
cd build
../source/configure --prefix="$ROOT/install" --without-x --with-readline=no --disable-debug --enable-cider --enable-openmp > ../configure.log 2>&1
make -j2 > ../make.log 2>&1
make install > ../install.log 2>&1
"$ROOT/install/bin/ngspice" --version > ../version.txt 2>&1
date -u +%FT%TZ > ../build_finished.txt
