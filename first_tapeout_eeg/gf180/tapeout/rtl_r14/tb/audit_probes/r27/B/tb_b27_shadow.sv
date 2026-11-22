// tb_b27_shadow - audit round 27 (B): step 3's read-back of a shadow (OFF_M_L, 0x21) after a write that the chip
// did not take (its frame slipped: FRAME_ERR), when the read-back slips once. M 218 (0xDA) -> 219 (0xDB) in RUN.
`timescale 1ns / 1ps
`default_nettype none
module tb_b27_shadow;
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

    // a 3-byte frame in which the chip misses host pulse `miss` (SCLK not raised for it; the host still samples)
    task automatic xfer_slip(input logic [23:0] tx, input integer miss, output logic [23:0] rx);
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
    endtask

    logic [7:0] v, e, c;
    logic [23:0] rx;
    integer hits;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);                              // RESET_FLAG cleared (CRC off)
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;           // CRC on
        r14_write(7'h52, 8'd29);                              // T_REC minimum
        r14_write(7'h22, 8'h02);                              // range 2, sign 0
        r14_write(7'h20, 8'h00);
        r14_write(7'h21, 8'hDA);                              // M = 218
        r14_cmd(8'h11);                                       // START
        do begin #(500000.0); r14_read(7'h04, v); end while (v !== 8'd6);
        $display("RUN; shadow M = %0d, active M = %0d", dut.u_regs.s_m, dut.u_regs.a_m);
        r14_read(7'h06, e); r14_write(7'h06, e);
        r14_read(7'h06, e); $display("ERR before the step: 0x%02h", e);
        // step 3: the new shadow value 0xDB, the frame slips (the chip misses pulse 20): FRAME_ERR, not written
        c = tb_crc8_update(tb_crc8_update(8'h00, 8'h21), 8'hDB);
        xfer_slip({8'h21, 8'hDB, c}, 20, rx);
        $display("OFF_M_L write (slipped): MISO %06h (rule (a): fixed bits %b, zeros %0d)", rx, rx[23:22] == 2'b10,
                 rx[15:0] == 16'h0000);
        r14_read(7'h06, e); $display("ERR 0x%02h (FRAME_ERR: the write was not taken); chip's shadow M = %0d", e, dut.u_regs.s_m);
        r14_read(7'h21, v); $display("OFF_M_L, a clean read-back: 0x%02h", v);
        hits = 0;
        for (int k = 0; k < 24; k++) begin
            xfer_slip({8'hA1, 16'h0000}, k, rx);
            if (rx[23:22] == 2'b10 && rx[7:0] == tb_crc8_update(tb_crc8_update(8'h00, 8'hA1), rx[15:8]) &&
                rx[15:8] != dut.u_regs.s_m[7:0]) begin
                hits = hits + 1;
                $display("read-back, chip misses pulse %0d: host reads %06h -> CRC valid, rule (a) passes, OFF_M_L = 0x%02h (chip 0x%02h)",
                         k, rx, rx[15:8], dut.u_regs.s_m[7:0]);
            end
        end
        $display("%0d slipped read-backs pass as the written value", hits);
        r14_read(7'h06, e); $display("ERR after 0x%02h; chip's shadow M %0d, active M %0d", e, dut.u_regs.s_m, dut.u_regs.a_m);
        $finish;
    end
endmodule
`default_nettype wire
