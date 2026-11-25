// tb_b45_window - audit round 45, auditor B: step 5 (ii)'s window method timed by the formula of requirements 5.4
// ("from the host's CS_N fall: t_css + 7.5 us (1 MHz) / 3.75 us (2 MHz) + 3 MCLK") with SCLK duty cycles that spec
// 3.1 allows (high >= 4 MCLK, low >= 5 MCLK, <= 2 MHz). One chip in RUN, CRC on, level mode; the chip is compared
// with itself (exactly aligned), so the first FIFO_LEVEL read must return 0 whenever w >= 3 MCLK (host error 0).
`timescale 1ns / 1ps
`default_nettype none
module tb_b45_window2;
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

    real hi [0:3] = '{500.0, 1000.0 - (5.0 * TMCLK + 0.3), 250.0, 500.0 - (5.0 * TMCLK + 0.3)};
    real lo [0:3] = '{500.0, 5.0 * TMCLK + 0.3, 250.0, 5.0 * TMCLK + 0.3};
    real per[0:3] = '{1000.0, 1000.0, 500.0, 500.0};
    integer nbad = 0;
    real t_m0, per_m;
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
        for (int c = 0; c < 4; c++) begin
            for (int off = 0; off < 2; off++) begin
                for (int rep = 0; rep < 3; rep++) begin
                    spi_high = 250.0; spi_low = 250.0;
                    if (DRDY_N === 1'b1) @(negedge DRDY_N);   // this chip's output time (t_d: its DRDY_N fall)
                    readout();
                    if (DRDY_N !== 1'b1) $display("ERROR: DRDY_N not high after the read-out");
                    // the reference's predicted fall: this chip's next fall, or 1 MCLK later (this chip released
                    // 1 MCLK earlier than the reference: aligned within PIN-03 / step 5 (ii)'s 1 MCLK)
                    t_p = t_d + 32768.0 * per_m + off * per_m;
                    w = 3.0 * per_m;            // the minimum w (host timing error 0)
                    t_formula = spi_tcss + 7.5 * per[c] + 3.0 * per_m;   // requirements 5.4 step 5 (ii)
                    t_cs = t_p - w - t_formula - 7.7 * rep;              // earlier only (more margin)
                    #(t_cs - $realtime);
                    spi_high = hi[c]; spi_low = lo[c];
                    r14_read(7'h05, v);
                    $display("class %0d (high %0.1f / low %0.1f) chip %0d MCLK early: load %+0.1f ns vs the formula; load - reference's predicted fall %+0.1f ns; FIFO_LEVEL %0d%s",
                             c, hi[c], lo[c], off, (t_load - t_csf) - t_formula, t_load - t_p, v,
                             (v != 0) ? "  <- aligned chip judged advanced" : "");
                    if (v != 0) nbad = nbad + 1;
                end
            end
        end
        $display("tb_b45_window2: %0d of 24 first reads nonzero for an aligned chip", nbad);
        $finish;
    end
endmodule
`default_nettype wire
