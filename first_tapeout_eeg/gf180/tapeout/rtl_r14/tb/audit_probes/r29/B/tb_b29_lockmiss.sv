// tb_b29_lockmiss - audit round 29 (B): the lock write (TEST_KEY 0x00, CRC on) of step 3's test-register restore with
// one SCLK pulse missed by the chip in its data byte, in RUN (AFE_RST 0). Rule (a): MISO after the header all 0x00?
// ERR? Is the key still open after step 3's literal handling (ERR written back, every setting rewritten: TEST_KEY is
// write-only and not a setting the read-back or the rewrite names)?
`timescale 1ns / 1ps
`default_nettype none
module tb_b29_lockmiss;
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
    // a 3-byte frame in which the chip misses host pulse `miss` (the host samples MISO at each of its rises)
    task automatic xfer_miss(input logic [23:0] tx, input integer miss, output logic [23:0] rx);
        CS_N = 1'b0; MOSI = tx[23]; #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            if (n != miss) SCLK = 1'b1;
            rx[23 - n] = miso_pad;
            #(spi_high); SCLK = 1'b0;
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 < 24) #(spi_low);
        end
        #(spi_tcsh); CS_N = 1'b1; #(spi_tidle);
    endtask
    logic [7:0] e, v;
    logic [23:0] rx;
    integer nopen;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_read(7'h06, e); r14_write(7'h06, e);
        r14_cmd(8'h11);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        nopen = 0;
        for (int miss = 8; miss < 24; miss++) begin
            r14_write(7'h11, 8'h3C); r14_write(7'h60, 8'h00); r14_write(7'h61, 8'h00);   // restore, key open
            r14_read(7'h06, e); r14_write(7'h06, e);
            xfer_miss({8'h11, 8'h00, tb_crc8_update(tb_crc8_update(8'h00, 8'h11), 8'h00)}, miss, rx);   // the lock
            repeat (8) @(posedge MCLK);
            r14_read(7'h06, e);
            if (rx[23:22] == 2'b10 && rx[15:0] == 16'h0000) begin
                // rule (a) passed; ERR has a bit -> write ERR back, rewrite the settings written (TEST_MUX, TEST_CTRL:
                // still open, accepted), check ERR again
                r14_write(7'h06, e); r14_write(7'h60, 8'h00); r14_write(7'h61, 8'h00); r14_read(7'h06, v);
                if (dut.u_regs.unlocked) begin
                    nopen++;
                    $display("miss pulse %0d: rule (a) passed (MISO %06h), ERR 0x%02h; after the rewrite ERR 0x%02h, key %s",
                             miss, rx, e, v, dut.u_regs.unlocked ? "OPEN" : "locked");
                end
                r14_write(7'h06, v);
            end else begin
                r14_write(7'h06, e);
            end
            r14_write(7'h11, 8'h00);
        end
        $display("lock writes with one missed pulse in the data or CRC byte that leave the key open behind a clean ERR: %0d of 16", nopen);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
