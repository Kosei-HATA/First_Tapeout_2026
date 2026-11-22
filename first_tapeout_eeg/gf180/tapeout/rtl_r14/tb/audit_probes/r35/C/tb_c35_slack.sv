// tb_c35_slack (audit 35, C): Y's round-19 check (a frame ended mid-byte, the next one 4 MCLK + 0.3 ns after the CS_N
// rise): how many MCLK edges lie between ERR taking FRAME_ERR and the next header's STATUS copy, over 32 phases of
// the CS_N rise against MCLK
`timescale 1ns / 1ps
`default_nettype none
module tb_c35_slack;
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
    integer edge_n = 0, e_err = -1, e_copy = -1, mn = 999, mx = -1;
    always @(posedge MCLK) begin
        edge_n++;
        if (dut.u_spi.cs_start) e_copy = edge_n;                 // the copy is taken at this edge (end of cs_start's cycle)
    end
    logic [7:0] q;
    always @(negedge MCLK) begin
        if (dut.u_regs.err[ERR_FRAME_ERR_LSB] === 1'b1 && q[ERR_FRAME_ERR_LSB] !== 1'b1) e_err = edge_n;   // ERR changed at this edge
        q = dut.u_regs.err;
    end
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (200) @(posedge MCLK);
        for (int p = 0; p < 32; p++) begin
            r14_write(7'h08, 8'h02);                    // ALERT from FRAME_ERR only
            r14_write(7'h06, 8'hFF);
            #(p * TMCLK / 32.0);
            for (int i = 0; i < 16; i++) spi_tx[i] = 8'h00;
            spi_tx[0] = 8'h84;
            spi_tidle = 4.0 * TMCLK + 0.3;
            spi_xfer(1, 3);                             // CS_N rises inside the second byte: FRAME_ERR
            spi_tidle = 600.0;
            spi_xfer(2, 0);                             // the next frame, 4 MCLK + 0.3 ns later: its header copies STATUS
            if (e_copy - e_err < mn) mn = e_copy - e_err;
            if (e_copy - e_err > mx) mx = e_copy - e_err;
            if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b1) $display("phase %0d: no ALERT in the next header", p);
        end
        $display("edges from ERR's FRAME_ERR to the next header's copy: %0d .. %0d over 32 phases", mn, mx);
        $finish;
    end
endmodule
`default_nettype wire
