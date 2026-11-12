drc off
scalegrid 1 10
gds read input.gds
load inverter_link
select top cell
box values 0.87um 1.7um 0.87um 1.7um
label IN center metal1
port make 1
box values 101.43um 1.7um 101.43um 1.7um
label OUT center metal1
port make 2
box values 10.1um 1.7um 10.1um 1.7um
label AG1 center metal2
port make 3
box values 89.9um 1.7um 89.9um 1.7um
label AG2 center metal2
port make 4
extresist threshold 0
extresist minres 0.1
extresist mindelay 0
extresist simplify off
extract do local
extract do resistance
extract all
quit -noprompt
