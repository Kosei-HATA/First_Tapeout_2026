// tb_b24_copy - audit round 24, auditor B: one SCLK slip in a CRC read of an active copy (rule (c), step 4)
`timescale 1ns / 1ps
`default_nettype none
module tb_b24_copy;
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
    `include "spi_bfm_r14.svh"

    // a 3-byte transfer in which the chip misses host pulse `at` (8 ns long just after an MCLK edge), as tb_top_r14
    task automatic xfer_miss(input integer at);
        integer total;
        total = 24;
        CS_N = 1'b0;
        MOSI = spi_bit(0, 3);
        #(spi_tcss);
        for (int n = 0; n < total; n++) begin
            if (n == at) begin
                @(posedge MCLK); #2.0;
                SCLK = 1'b1; spi_rx[n / 8][7 - (n % 8)] = miso_pad; #8.0; SCLK = 1'b0;
                MOSI = (n + 1 < total) ? spi_bit(n + 1, 3) : 1'b0;
                if (n + 1 < total) #(spi_low);
            end else begin
                SCLK = 1'b1; spi_rx[n / 8][7 - (n % 8)] = miso_pad; #(spi_high); SCLK = 1'b0;
                MOSI = (n + 1 < total) ? spi_bit(n + 1, 3) : 1'b0;
                if (n + 1 < total) #(spi_low);
            end
        end
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
    endtask

    logic [7:0] v, c;
    initial begin
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (20) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;              // CRC on
        r14_write(7'h21, 8'hAA); r14_write(7'h22, 8'h02);        // M[7:0] = 0xAA (M = 170), range 2
        r14_cmd(8'h33);                                          // APPLY in IDLE: the active copies take the shadows
        repeat (3000) @(posedge MCLK);
        r14_read(7'h06, v); $display("ERR 0x%02h", v);
        r14_write(7'h06, v);
        r14_read(7'h31, v); $display("OFF_M_L.ACT (clean read) 0x%02h, CRC %s", v, (spi_rx[2] === tb_crc8_update(tb_crc8_update(8'h00, 8'hB1), v)) ? "ok" : "BAD");
        // the same read, the chip missing host pulse 14
        spi_tx[0] = 8'hB1; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
        xfer_miss(14);
        c = tb_crc8_update(tb_crc8_update(8'h00, 8'hB1), spi_rx[1]);
        $display("slipped read: host bytes %02h %02h %02h; rule (a) %s; host CRC check %s -> value 0x%02h",
                 spi_rx[0], spi_rx[1], spi_rx[2], (spi_rx[0][7:6] == 2'b10) ? "passes" : "fails",
                 (c === spi_rx[2]) ? "PASSES" : "fails", spi_rx[1]);
        r14_read(7'h06, v); $display("ERR after the slipped read 0x%02h (FRAME_ERR = bit 1)", v);
        $finish;
    end
endmodule
`default_nettype wire
