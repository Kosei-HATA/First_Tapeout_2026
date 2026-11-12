drc off
crashbackups stop
gds read input.gds
load mim_only
select top cell
box values 0.1um 0.1um 0.1um 0.1um
label TOP center mimcap
port make 1
box values -0.5um -0.5um -0.5um -0.5um
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
