// tb_r45_window_fix - audit round 45, the response to auditor B's finding: step 5 (ii)'s window method with the first
// FIFO_LEVEL read placed by the corrected formula of requirements 5.4 (from the host's CS_N fall: t_css + 7 T_SCLK +
// t_high + 3 MCLK) for SCLK shapes spec 3.1 allows (High >= 4 MCLK, Low >= 5 MCLK, 1 and 2 MHz: 50 % duty, the longest
// High and the shortest High). Adapted from auditor B's tb_b45_window2.sv (same chip setup: one chip in RUN, CRC on,
// level mode, compared with itself). The reference's predicted fall is placed k MCLK after this chip's own next fall:
// k = 0 (exactly aligned) and k = 1 (released 1 MCLK earlier, still aligned) must read 0; k = 6 (advanced by 6 MCLK,
// more than w) must read nonzero (the method still finds an advanced chip). Host timing error 0, w = 3 MCLK.
`timescale 1ns / 1ps
`default_nettype none
module tb_r45_window_fix;
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

    // the data byte's load (spec 3.2): the cycle in which the SPI loads the first byte after the header
    real t_csf, t_load;
    always @(negedge CS_N) begin t_csf = $realtime; t_load = -1.0; end
    always @(posedge MCLK)
        if (dut.u_spi.sclk_fall && dut.u_spi.bit_cnt == 3'd0 && dut.u_spi.st == 4'd2 && t_load < 0.0)
            t_load = $realtime;                 // the edge that loads reg_rdata into the shift register

    real t_d;
    always @(negedge DRDY_N) t_d = $realtime;

    task automatic readout();                   // samples until the empty word with DATA = 0
        logic [7:0] s; logic [15:0] q; logic [23:0] d; bit ok;
        for (int i = 0; i < 20; i++) begin
            r14_sample(s, q, d, ok);
            if (ok && !s[7] && !spi_status[2]) return;
        end
        $display("ERROR: readout did not end");
    endtask

    localparam int NC = 6;
    real hi [0:NC-1] = '{500.0, 1000.0 - (5.0 * TMCLK + 0.3), 4.0 * TMCLK + 0.3,
                         250.0, 500.0 - (5.0 * TMCLK + 0.3), 4.0 * TMCLK + 0.3};
    real per[0:NC-1] = '{1000.0, 1000.0, 1000.0, 500.0, 500.0, 500.0};
    int  ks [0:2] = '{0, 1, 6};
    integer n_aligned_bad = 0, n_adv_missed = 0, n_late = 0, n_reads = 0;
    real t_m0, per_m, worst = -1.0e9;
    initial begin
        logic [7:0] v;
        real t_p, t_formula, t_cs, w;
        spi_tcss = 300.0;
        @(posedge MCLK); t_m0 = $realtime; repeat (1000) @(posedge MCLK); per_m = ($realtime - t_m0) / 1000.0;
        #7.3 RESET_N = 1'b1;
        #2000.0;
        r14_write(7'h55, 8'h01);                // IF_CFG: CRC on (level mode)
        bfm_crc_en = 1'b1;
        r14_write(7'h09, 8'h00);                // ALERT_MASK_D = 0 (step 3)
        r14_cmd(CMD_START);
        wait (dut.seq_state == ST_RUN);
        $display("simulated MCLK period %0.6f ns; 1 ms = 32768 of them", per_m);
        for (int c = 0; c < NC; c++) begin
            for (int kk = 0; kk < 3; kk++) begin
                for (int rep = 0; rep < 3; rep++) begin
                    spi_high = 250.0; spi_low = 250.0;
                    if (DRDY_N === 1'b1) @(negedge DRDY_N);   // this chip's output time (t_d: its DRDY_N fall)
                    readout();
                    if (DRDY_N !== 1'b1) $display("ERROR: DRDY_N not high after the read-out");
                    t_p = t_d + 32768.0 * per_m + ks[kk] * per_m;
                    w = 3.0 * per_m;            // the minimum w (host timing error 0)
                    // the corrected formula (requirements 5.4 step 5 (ii), audit round 45)
                    t_formula = spi_tcss + 7.0 * per[c] + hi[c] + 3.0 * per_m;
                    t_cs = t_p - w - t_formula - 7.7 * rep;
                    #(t_cs - $realtime);
                    spi_high = hi[c]; spi_low = per[c] - hi[c];
                    r14_read(7'h05, v);
                    n_reads = n_reads + 1;
                    if ((t_load - t_csf) - t_formula > worst) worst = (t_load - t_csf) - t_formula;
                    if ((t_load - t_csf) - t_formula > 0.0) n_late = n_late + 1;
                    $display("SCLK %0.0f kHz high %0.1f / low %0.1f, reference's fall %0d MCLK later: load %+0.1f ns vs the formula; FIFO_LEVEL %0d%s",
                             1.0e6 / per[c], hi[c], per[c] - hi[c], ks[kk], (t_load - t_csf) - t_formula, v,
                             (ks[kk] <= 1 && v != 0) ? "  <- ERROR: aligned chip judged advanced" :
                             (ks[kk] > 1 && v == 0) ? "  <- ERROR: advanced chip not found" : "");
                    if (ks[kk] <= 1 && v != 0) n_aligned_bad = n_aligned_bad + 1;
                    if (ks[kk] > 1 && v == 0) n_adv_missed = n_adv_missed + 1;
                end
            end
        end
        $display("tb_r45_window_fix: %0d reads; aligned chips read nonzero %0d times, the 6-MCLK advanced chip read 0 %0d times; loads after the formula %0d (latest %+0.1f ns)",
                 n_reads, n_aligned_bad, n_adv_missed, n_late, worst);
        if (n_aligned_bad == 0 && n_adv_missed == 0 && n_late == 0) $display("PASS");
        else $display("FAIL");
        $finish;
    end
endmodule
`default_nettype wire
