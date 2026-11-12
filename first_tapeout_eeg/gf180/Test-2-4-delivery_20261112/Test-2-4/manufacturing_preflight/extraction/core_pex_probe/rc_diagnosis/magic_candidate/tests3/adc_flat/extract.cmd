drc off
scalegrid 1 10
gds read input.gds
load adc_flat
select top cell
box values 1.1um 0.5um 1.1um 0.5um
label TOP center metal4
port make 1
box values 0.5um 3.5um 0.5um 3.5um
label BOT center metal4
port make 2

extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do local
extract do resistance
extract all
quit -noprompt
