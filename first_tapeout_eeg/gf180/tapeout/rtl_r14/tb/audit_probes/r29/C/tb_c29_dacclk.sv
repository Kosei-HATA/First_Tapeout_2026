// Audit round 29 (C): DAC_CLK while RESET_N is low (MCLK running, then MCLK stopped), and the first frame after the
// release: prints DAC_CLK at every MCLK edge in reset and the edges of DAC_CLK after it
`timescale 1ns / 1ps
module tb_c29_dacclk;
    logic MCLK = 0, RESET_N = 0, SCLK = 0, CS_N = 1, MOSI = 0;
    logic [4:0] CODE = 5'd15;
    wire MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN, CMP_STROBE, DAC_CLK, CHOP,
         CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    eeg_digital_top dut (.*);
    bit run = 1;
    always #15.259 if (run) MCLK = ~MCLK;
    integer hi_rst = 0, n_rst = 0, rises = 0;
    always @(posedge MCLK) if (!RESET_N) begin n_rst++; if (DAC_CLK !== 1'b0) hi_rst++; end
    always @(posedge DAC_CLK) rises++;
    initial begin
        repeat (20) @(posedge MCLK);
        $display("RESET_N low, MCLK running: DAC_CLK %b (not 0 at %0d of %0d edges)", DAC_CLK, hi_rst, n_rst);
        RESET_N = 1;
        repeat (100) @(posedge MCLK);
        $display("after the release: %0d DAC_CLK rises in 100 MCLK (3 frames)", rises);
        run = 0; #100;
        rises = 0;
        RESET_N = 0; #1;
        $display("RESET_N low with MCLK stopped: DAC_CLK %b, a rising edge at the assertion: %0d", DAC_CLK, rises);
        $finish;
    end
endmodule
