// tb_b31_bounce - audit round 31 (B): a bounce inside SCLK pulse k's high phase (a 2-MCLK dip the chip sees as an
// extra fall and rise) during a 3-byte CRC read; prints what the host samples, to compare with the slip model's third
// kind (MOSI bit k read twice, MISO bit k+1 skipped). Registers: STATUS (0x03), STATE (0x04), ERR (0x06), T_WARM (0x50).
`timescale 1ns / 1ps
`default_nettype none
module tb_b31_bounce;
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
    task automatic xfer_bounce(input logic [23:0] tx, input integer k, output logic [23:0] rx, output logic [7:0] st);
        CS_N = 1'b0;
        MOSI = tx[23];
        #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            SCLK = 1'b1;
            rx[23 - n] = miso_pad;
            if (n == k) begin                     // high 3 MCLK, dip 2 MCLK, high 3 MCLK (MOSI unchanged)
                #(3.0 * TMCLK); SCLK = 1'b0; #(2.0 * TMCLK); SCLK = 1'b1; #(3.0 * TMCLK);
            end else #(spi_high);
            SCLK = 1'b0;
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 < 24) #(spi_low);
        end
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
    endtask
    logic [23:0] rx;
    logic [7:0] st, v;
    integer fd;
    logic [6:0] regs [0:3] = '{7'h03, 7'h04, 7'h06, 7'h50};
    initial begin
        fd = $fopen("bounce_rtl.txt", "w");
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        for (int r = 0; r < 4; r++) begin
            for (int k = 0; k < 24; k++) begin
                // the chip's state just before: STATUS, the register values (logged so the model uses the same)
                $fwrite(fd, "%02h %0d %02h %02h %02h %02h %02h", regs[r], k, dut.u_regs.status_byte, dut.u_regs.err,
                        {4'd0, dut.u_seq.state}, dut.u_regs.r_tw, dut.u_regs.status_byte);
                xfer_bounce({1'b1, regs[r], 16'h0000}, k, rx, st);
                $fwrite(fd, " %06h %02h\n", rx, dut.u_regs.err);
                r14_write(7'h06, 8'hFE);          // clear what the bounced frame set (keep RESET_FLAG as is)
            end
        end
        $fclose(fd);
        $finish;
    end
endmodule
