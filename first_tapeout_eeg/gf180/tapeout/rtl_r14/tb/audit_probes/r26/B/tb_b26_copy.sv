// tb_b26_copy - audit round 26 (B): step 4's effect check of an APPLY_NR that was NOT executed (its frame lost to a
// CRC error), M 170 -> 171 in RUN, when the confirming CRC read of OFF_M_L's active copy (0x31) slips once.
`timescale 1ns / 1ps
`default_nettype none
module tb_b26_copy;
`include "eeg_regs_defs.svh"
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
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"

    // a 3-byte CRC read in which the chip misses host pulse `miss` (0..23; -1: none): SCLK is not raised for it, the
    // host still samples MISO at that time and keeps its own MOSI schedule
    task automatic read_slip(input logic [6:0] addr, input integer miss, output logic [7:0] b0, b1, b2);
        logic [23:0] tx, rx;
        tx = {1'b1, addr, 16'h0000};
        CS_N = 1'b0;
        MOSI = tx[23];
        #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            if (n != miss) SCLK = 1'b1;
            rx[23 - n] = miso_pad;
            #(spi_high);
            SCLK = 1'b0;
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 < 24) #(spi_low);
        end
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
        {b0, b1, b2} = rx;
    endtask

    logic [7:0] v, b0, b1, b2, e;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);                              // RESET_FLAG cleared (CRC off)
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;           // CRC on
        r14_write(7'h52, 8'd29);                              // T_REC minimum (a shorter start)
        r14_write(7'h22, 8'h02);                              // range 2, sign 0
        r14_write(7'h20, 8'h00);
        r14_write(7'h21, 8'hAA);                              // M = 170 = 0x0AA
        r14_cmd(8'h11);                                       // START
        do begin #(500000.0); r14_read(7'h04, v); end while (v !== 8'd6);
        $display("RUN; active M = %0d (OFF_M_L.ACT 0x%02h)", dut.u_regs.a_m, dut.u_regs.a_m[7:0]);
        r14_read(7'h06, e); r14_write(7'h06, e);              // ERR cleared
        r14_read(7'h06, e); $display("ERR before the step: 0x%02h", e);
        // the step 170 -> 171: shadow written and read back, then APPLY_NR whose frame fails its CRC
        r14_write(7'h21, 8'hAB);
        r14_read(7'h21, v); $display("shadow OFF_M_L read back 0x%02h", v);
        spi_tx[0] = 8'h10; spi_tx[1] = 8'h44; spi_tx[2] = tb_crc8_update(tb_crc8_update(8'h00, 8'h10), 8'h44) ^ 8'h01;
        spi_xfer(3, 0);
        $display("APPLY_NR frame: MISO %02h %02h %02h (rule (a) passes: fixed bits, zeros)", spi_rx[0], spi_rx[1], spi_rx[2]);
        #(20000.0);                                           // > 17 frames
        r14_read(7'h03, v); $display("STATUS 0x%02h (CMD_PENDING %0d)", v, v[4]);
        r14_read(7'h06, e); $display("ERR 0x%02h (CRC_ERR: the APPLY_NR was not executed)", e);
        r14_read(7'h31, v); $display("OFF_M_L.ACT, a clean read: 0x%02h; chip's active M = %0d", v, dut.u_regs.a_m);
        for (int k = 0; k < 24; k++) begin
            read_slip(7'h31, k, b0, b1, b2);
            if (b0[7:6] == 2'b10 && b2 == tb_crc8_update(tb_crc8_update(8'h00, 8'hB1), b1) && b1 != dut.u_regs.a_m[7:0])
                $display("chip misses pulse %0d: host reads %02h %02h %02h -> CRC valid, rule (a) passes, OFF_M_L.ACT = 0x%02h (true 0x%02h)",
                         k, b0, b1, b2, b1, dut.u_regs.a_m[7:0]);
        end
        r14_read(7'h06, e); $display("ERR after the slipped reads 0x%02h; chip's active M still %0d", e, dut.u_regs.a_m);
        $finish;
    end
endmodule
`default_nettype wire
