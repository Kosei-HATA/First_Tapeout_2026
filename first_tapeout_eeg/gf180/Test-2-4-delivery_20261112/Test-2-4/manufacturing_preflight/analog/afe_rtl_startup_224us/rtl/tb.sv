`timescale 1ns/1ps
module tb;
reg MCLK=0, RESET_N=0,SCLK=0,CS_N=1,MOSI=0;
wire CHOP,CHOP_OUT,CHOP_BLANK,AFE_RST,CHOP_EN,ADC_RST_N;
wire [3:0] CPF_TRIM;wire [1:0] AFE_IBIAS,BTRIM_P,BTRIM_N;
wire [9:0] OFM;wire OFS;wire [3:0] OFEN;
eeg_digital_top dut(.MCLK(MCLK),.RESET_N(RESET_N),.SCLK(SCLK),.CS_N(CS_N),.MOSI(MOSI),.CODE(5'd16),.CHOP(CHOP),.CHOP_OUT(CHOP_OUT),.CHOP_BLANK(CHOP_BLANK),.AFE_RST(AFE_RST),.CHOP_EN(CHOP_EN),.ADC_RST_N(ADC_RST_N),.CPF_TRIM(CPF_TRIM),.AFE_IBIAS(AFE_IBIAS),.BTRIM_P(BTRIM_P),.BTRIM_N(BTRIM_N),.OFM(OFM),.OFS(OFS),.OFEN(OFEN));
integer f;real next_edge;integer i;
initial begin
 f=$fopen("controls.csv","w");
 $fdisplay(f,"time_ns,reset_n,adc_rst_n,chop,chop_out,blank,afe_rst,chop_en,cpf,ibias,bp,bn,ofm,ofs,ofen");
 #0.001; RESET_N=1; #0.001; RESET_N=0;
 #2999.998; RESET_N=1;
 #5000; CS_N=0; #500;
 send_byte(8'h20);send_byte(8'h02);send_byte(8'h64);
 #500;CS_N=1;
 #500;
 if(AFE_RST!==0 || CHOP_EN!==1 || CPF_TRIM!==8 || AFE_IBIAS!==2) $fatal(1,"Register/trim check failed");
 $display("SPI CHECK PASS time=%0.3f ns CONTROL=0x64 AFE_RST=%b CHOP_EN=%b",$realtime,AFE_RST,CHOP_EN);
 #234500;$fclose(f);$finish;
end
initial begin
 next_edge=2000.0;
 for(i=0;i<20000;i=i+1)begin #(next_edge-$realtime);MCLK=~MCLK;next_edge=2000.0+(i+1)*(1000.0/32.768/2);end
end
task send_byte(input [7:0] b);integer j;begin
 for(j=7;j>=0;j=j-1)begin MOSI=b[j];#250;SCLK=1;#250;SCLK=0;end
end endtask
always @(RESET_N or ADC_RST_N or CHOP or CHOP_OUT or CHOP_BLANK or AFE_RST or CHOP_EN or CPF_TRIM or AFE_IBIAS or BTRIM_P or BTRIM_N or OFM or OFS or OFEN)begin
 #0.002;
 $fdisplay(f,"%0.3f,%b,%b,%b,%b,%b,%b,%b,%d,%d,%d,%d,%d,%b,%d",$realtime,RESET_N,ADC_RST_N,CHOP,CHOP_OUT,CHOP_BLANK,AFE_RST,CHOP_EN,CPF_TRIM,AFE_IBIAS,BTRIM_P,BTRIM_N,OFM,OFS,OFEN);
end
endmodule

