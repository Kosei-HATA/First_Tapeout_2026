drc off
scalegrid 1 10
gds read input.gds
load two_mim_internal
select top cell
box values 50um 49.5um 50um 49.5um
label res:force@ center metal5
label res:drive@ center metal5
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do local
extract do resistance
extract all
quit -noprompt
