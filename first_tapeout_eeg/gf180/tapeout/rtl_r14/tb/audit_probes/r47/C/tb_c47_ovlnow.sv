// audit round 47, auditor C: OVL_NOW (STATUS bit 1, the value a header copies) around the edge that takes the 4th
// extreme code: in every MCLK cycle of that frame, print the frame cycle, ovl_now and STATUS's OVL_NOW bit
`timescale 1ns / 1ps
`default_nettype none
module tb_c47_ovlnow;
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG;
    wire [3:0] CPF_TRIM, OFEN;
    wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    integer nfr = 0, f0;
    always @(posedge MCLK) if (dut.cycle == 5'd1) begin   // CODE changes at e2, as the ADC's
        CODE <= (nfr >= f0 && nfr < f0 + 4) ? 5'd31 : 5'd16;
        nfr <= nfr + 1;
    end
    initial begin
        f0 = 100;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        wait (nfr == f0 + 3);
        repeat (40) begin
            @(negedge MCLK);
            $display("frame %0d cycle %0d: ovl_now %b, STATUS 0x%02h (OVL_NOW bit %b), cic_en %b", nfr - 1, dut.cycle,
                     dut.ovl_now, dut.status_byte, dut.status_byte[1], dut.cic_en);
        end
        $finish;
    end
endmodule
`default_nettype wire
