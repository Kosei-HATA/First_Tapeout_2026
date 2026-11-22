// tb_c35_hdr (audit 35, C): the header's STATUS when ALERT rises at the edge that starts the copy's cycle (spec 3.2:
// STATUS is copied at the CS_N fall; the cycle in which the SPI sees the synchronized fall). FRAME_ERR is forced in the
// cycle before the copy (CS_N low has entered the synchronizer), so ERR and ALERT change at the copy cycle's start
`timescale 1ns / 1ps
`default_nettype none
module tb_c35_hdr;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    `include "spi_bfm_r14.svh"
    logic [7:0] v, st;
    bit arm = 1'b0;
    integer n_forced = 0, errors = 0;
    always @(negedge MCLK) begin
        if (arm && dut.u_spi.cs_q == 3'b110 && dut.u_spi.armed) begin   // q0 low, q1 and q2 high: cs_start next cycle
            force dut.u_spi.frame_err = 1'b1;
            n_forced++;
            arm = 1'b0;
            @(negedge MCLK);
            release dut.u_spi.frame_err;
            if (dut.u_spi.cs_start !== 1'b1) $display("SETUP: no cs_start in the cycle after the forced FRAME_ERR");
        end
    end
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (200) @(posedge MCLK);
        r14_write(7'h06, 8'hFF);                        // RESET_FLAG cleared: ALERT 0
        r14_read(7'h03, st);
        $display("STATUS 0x%02h before (ALERT 0 expected)", st);
        arm = 1'b1;
        r14_read(7'h06, v);                             // its header carries STATUS, copied at the CS_N fall
        if (n_forced != 1) begin errors++; $display("not exercised"); end
        else if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b1 || v[ERR_FRAME_ERR_LSB] !== 1'b1) begin
            errors++;
            $display("FAIL: header STATUS 0x%02h (ALERT %b), ERR 0x%02h: ALERT was 1 in the copy's cycle (spec 3.2)",
                     spi_rx[0], spi_rx[0][STATUS_ALERT_LSB], v);
        end else $display("ok: header STATUS 0x%02h with ALERT, ERR 0x%02h", spi_rx[0], v);
        $display("%s: tb_c35_hdr (%0d errors)", errors == 0 ? "PASS" : "FAIL", errors);
        $finish;
    end
endmodule
`default_nettype wire
