// audit 37 A probe: a one-step APPLY_NR pending in RECOVER and taken at the very tick where RECOVER expires
// (T_ELEC 0), both chopper rates, the APPLY that leads into RECOVER at 16 positions of the output interval.
// Checks: the OFM edge and the RECOVER -> ALIGN move happen at the same e25; the CIC clear (ALIGN's output time) and
// the first store follow; the first stored window's first input (cycle 3 of the frame after the clear) integrates
// from e0 of the clear's frame, which must be >= 167 MCLK after the OFM edge (the same bound as RUN's first unmarked
// window and ALIGN's APPLY_NR); no sample of that RUN carries CHANGED (no mark outside RUN).
`timescale 1ns / 1ps
`default_nettype none
module tb_a37_recexp;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd13 + 5'($urandom % 6);
    integer mclk = 0;
    integer n_ofm = 0, m_ofm = 0, m_align = 0, m_clear = 0, m_store = 0, errs = 0, n_ok = 0, n_chg = 0;
    logic [3:0] st_q = 4'd0;
    logic [9:0] ofm_q = 10'd0;
    // one monitor, 1 ns after every rising edge: mclk counts that edge, the registers show their new values
    always @(posedge MCLK) begin
        #1;
        mclk = mclk + 1;
        if (OFM !== ofm_q) begin n_ofm = n_ofm + 1; m_ofm = mclk; end
        ofm_q = OFM;
        if (st_q == ST_RECOVER && dut.seq_state == ST_ALIGN) m_align = mclk;
        st_q = dut.seq_state;
        if (dut.cic_stb && dut.seq_state == ST_ALIGN) m_clear = mclk;              // e8 of the clear's output frame
        if (dut.cic_stb && dut.seq_state == ST_FILL && dut.cic_valid) m_store = mclk;
        if (dut.seq_store && dut.smp_status[SMP_CHANGED_LSB]) n_chg = n_chg + 1;
    end
    task automatic wait_state(input logic [3:0] s);
        integer n; n = 0;
        while (dut.seq_state !== s && n < 8000000) begin @(posedge MCLK); n = n + 1; end
        if (n >= 8000000) begin $display("TIMEOUT state %0d", s); $finish; end
    endtask
    task automatic cmd(input logic [7:0] c);
        r14_cmd(c);
        while (dut.cmd_valid === 1'b1) @(posedge MCLK);
    endtask
    integer k, rate, d_step, mn, mx, m;
    initial begin
        spi_high = 130.0; spi_low = 160.0;                  // within the limits (4 and 5 MCLK): a 2-byte write in ~5 us
        repeat (5) @(posedge MCLK); RESET_N = 1'b1; repeat (20) @(posedge MCLK);
        m = 40;
        for (rate = 1; rate >= 0; rate = rate - 1) begin
            r14_write(7'h26, 8'(rate));
            r14_write(7'h22, 8'h01); r14_write(7'h20, 8'h00); r14_write(7'h21, 8'(m));
            if (dut.seq_state == ST_IDLE) cmd(8'h11); else cmd(8'h33);
            wait_state(ST_RUN);
            mn = 1000000; mx = -1;
            for (k = 0; k < 16; k = k + 1) begin
                @(posedge MCLK); while (!dut.cic_stb) @(posedge MCLK);
                #(k * 62500.0);
                cmd(8'h33);                                     // APPLY in RUN (no change): PRE, PULSE, RECOVER
                wait_state(ST_RECOVER);
                m = m + 1;
                r14_write(7'h21, 8'(m));                         // one step up
                // put APPLY_NR's commit just before the tick that ends RECOVER: wait until the timer is 0 and the
                // next tick is at least 2 frames away is not needed; commit when the timer is <= 8 frames
                // the APPLY_NR's commit between the last tick before the expiry and the expiry's tick
                while (dut.u_seq.timer > (rate ? 18'd7 : 18'd15)) @(posedge MCLK);
                cmd(8'h44);
                wait_state(ST_ALIGN);
                if (m_ofm != m_align) begin
                    errs = errs + 1;
                    $display("ERROR %0d kHz k=%0d: OFM edge at %0d, RECOVER->ALIGN at %0d (expected the same tick)", rate ? 128 : 64, k, m_ofm, m_align);
                end
                wait_state(ST_RUN);
                // the first stored window integrates from e0 of the clear's frame (cycle 8 -> 8 MCLK before)
                d_step = (m_clear - 8) - m_ofm;
                if (d_step < mn) mn = d_step;
                if (d_step > mx) mx = d_step;
                if (d_step < 167) begin
                    errs = errs + 1;
                    $display("ERROR %0d kHz k=%0d: first window starts %0d MCLK after the step (< 167)", rate ? 128 : 64, k, d_step);
                end
                if (OFM !== 10'(m) || dut.u_regs.a_m !== 10'(m)) begin
                    errs = errs + 1;
                    $display("ERROR: OFM %0d active M %0d, expected %0d", OFM, dut.u_regs.a_m, m);
                end
                n_ok = n_ok + 1;
            end
            $display("%0d kHz: APPLY_NR at RECOVER's expiring tick x16: step and ALIGN on the same e25; first window %0d .. %0d MCLK after the step",
                     rate ? 128 : 64, mn, mx);
        end
        if (n_chg != 0) begin errs = errs + 1; $display("ERROR: %0d CHANGED samples (no mark outside RUN)", n_chg); end
        $display("tb_a37_recexp: %0d cases, %0d errors", n_ok, errs);
        $finish;
    end
endmodule
`default_nettype wire
