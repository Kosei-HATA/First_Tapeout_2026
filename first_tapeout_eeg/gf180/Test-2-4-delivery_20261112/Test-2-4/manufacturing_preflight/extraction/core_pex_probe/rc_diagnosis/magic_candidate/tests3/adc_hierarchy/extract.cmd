drc off
scalegrid 1 10
gds read input.gds
load adc_c2
select top cell
extract do local
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do resistance
extract all
quit -noprompt
