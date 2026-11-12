drc off
scalegrid 1 10
gds read input.gds
load two_mim_internal
select top cell
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do local
extract do resistance
extract all
quit -noprompt
