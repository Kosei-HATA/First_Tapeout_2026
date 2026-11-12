drc off
scalegrid 1 10
gds read input.gds
load coupled_wires
select top cell
box values 1um 0.5um 1um 0.5um
label A center metal1
port make 1
box values 99um 0.5um 99um 0.5um
label B center metal1
port make 2

box values 1um 0.5um 1um 0.5um
label C center metal2
port make 3
box values 99um 0.5um 99um 0.5um
label D center metal2
port make 4
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do local
extract do resistance
extract all
quit -noprompt
