// tb_b33_probe_mosi - audit round 33 (B): the CRC-mode probe [0xD5, 0x00, 0x00] (host steps 2, 9, rule (c)) with one
// MOSI bit flipped in its header, on a chip with CRC on and on one with CRC off, at the timer values that matter
// (T_RST 0x22, T_REC 0x30) and at the defaults. Prints what the host sees and how it classifies the answer:
// "on" = byte 2 bit 0 set and byte 3 = CRC-8(0xD5, byte 2); "off" = byte 2 bit 0 clear and byte 3 = 0x00.
`timescale 1ns / 1ps
`default_nettype none
module tb_b33_probe_mosi;
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
    function automatic logic [7:0] c2(input logic [7:0] a, input logic [7:0] b);
        return tb_crc8_update(tb_crc8_update(8'h00, a), b);
    endfunction
    integer n_off_on, n_on_off;
    task automatic sweep(input string tag, input bit chip_crc);
        logic [7:0] s, d, c, h;
        string cls;
        for (int k = 0; k < 8; k++) begin
            h = 8'hD5 ^ (8'h01 << k);
            spi_tx[0] = h; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
            spi_xfer(3, 0);
            s = spi_rx[0]; d = spi_rx[1]; c = spi_rx[2];
            if (s[7:6] != 2'b10) cls = "rule(a) fails";
            else if (d[0] && c == c2(8'hD5, d)) cls = "ON";
            else if (!d[0] && c == 8'h00) cls = "OFF";
            else cls = "neither (retry)";
            $display("%s: header %02h (bit %0d flipped) -> host sees %02h %02h %02h: %s (chip CRC_EN %0d)", tag, h, k, s, d,
                     c, cls, dut.crc_en);
            if (chip_crc && cls == "OFF") n_on_off++;
            if (!chip_crc && cls == "ON") n_off_on++;
            // clear what the flipped frame set, in the chip's own format
            spi_tx[0] = 8'h06; spi_tx[1] = 8'hFE; spi_tx[2] = c2(8'h06, 8'hFE);
            spi_xfer(chip_crc ? 3 : 2, 0);
        end
    endtask
    initial begin
        n_off_on = 0; n_on_off = 0;
        spi_high = 500.0; spi_low = 500.0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        sweep("CRC off, defaults", 1'b0);
        r14_write(7'h54, 8'h25);                      // T_RST 37 with CRC off (the procedure never does this)
        sweep("CRC off, T_RST 0x25", 1'b0);
        r14_write(7'h54, 8'h0D);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        sweep("CRC on, defaults", 1'b1);
        r14_write(7'h54, 8'h22);
        sweep("CRC on, T_RST 0x22", 1'b1);
        r14_write(7'h54, 8'h0D); r14_write(7'h52, 8'h30);
        sweep("CRC on, T_REC 0x30", 1'b1);
        $display("tb_b33_probe_mosi: CRC-on chip read as CRC off %0d times (R/W flip excluded: counted too), CRC-off chip read as on %0d times; %0d SPI notes",
                 n_on_off, n_off_on, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
