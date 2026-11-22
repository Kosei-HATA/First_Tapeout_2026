// tb_a32_rate - audit round 32 (A) probe. eeg_digital_top through its pins (SPI BFM, CRC off, 2 MHz):
//  P1  APPLY in RUN that toggles CHOP_FAST, committed at swept offsets: per APPLY the tick's frame (mod 16, own
//      frame count from CMP_STROBE), PRE length, AFE_RST high length, where the CHOP rate actually switches (own
//      half-period measurement on the CHOP pin), all in frames
//  P3  every command: frames from its commit (reg_we on COMMAND) to the tick that takes it (cmd_ack)
//  P2  an APPLY_NR (+1 step) committed in ALIGN (T_ELEC 0) and in RUN: frames from the OFM pin change to the CIC
//      clear (ALIGN -> FILL) or to the output time ending the first marked interval
`timescale 1ns / 1ps
`default_nettype none
module tb_a32_rate4;
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

    // own frame count (CMP_STROBE high in cycle 0) and MCLK count
    integer fr = -1, mc = 0;
    always @(posedge MCLK) begin
        mc = mc + 1;
        #0.1;
        if (CMP_STROBE === 1'b1) fr = fr + 1;
    end
    // CHOP half periods: the time of the first half period of 256 MCLK after a run of 128 (and back)
    integer last_chop_mc = 0, half = 0, prev_half = 0, sw_mc = -1;
    always @(CHOP) if (RESET_N) begin
        prev_half = half;
        half = mc - last_chop_mc;
        last_chop_mc = mc;
        if (prev_half != 0 && half != prev_half && half != 0) sw_mc = mc - half;   // the edge that started the new half
    end
    // AFE_RST edges
    integer afe_rise_mc = 0, afe_fall_mc = 0;
    always @(posedge AFE_RST) afe_rise_mc = mc;
    always @(negedge AFE_RST) afe_fall_mc = mc;
    // state entries
    integer st_mc [0:15];
    integer st_fr [0:15];
    always @(dut.seq_state) begin st_mc[dut.seq_state] = mc; st_fr[dut.seq_state] = fr; end
    // P3: command commit -> ack
    integer commit_mc = -1, max_lat = 0, nlat = 0;
    always @(posedge MCLK) begin
        if (dut.cmd_ack === 1'b1 && commit_mc >= 0) begin
            if (mc - commit_mc > max_lat) max_lat = mc - commit_mc;
            nlat = nlat + 1;
            commit_mc = -1;
        end
        if (dut.reg_we === 1'b1 && dut.reg_addr === 7'h10 && dut.u_regs.w_ok === 1'b1) commit_mc = mc;
    end
    // OFM pin change
    integer ofm_mc = 0, ofm_fr = 0;
    always @(OFM) begin ofm_mc = mc; ofm_fr = fr; end
    integer out_mc = 0;                       // last output time (cic_stb)
    always @(posedge MCLK) if (dut.cic_stb === 1'b1) out_mc = mc;

    task automatic wait_state(input logic [3:0] s);
        integer n;
        n = 0;
        while (dut.seq_state !== s && n < 4000000) begin @(posedge MCLK); n = n + 1; end
        if (n >= 4000000) begin $display("TIMEOUT waiting for state %0d", s); $finish; end
    endtask
    task automatic cmd(input logic [7:0] c);
        r14_cmd(c);
        while (dut.cmd_valid === 1'b1) @(posedge MCLK);
    endtask

    integer i, fast, pre_fr, pulse_fr, tick_fr, n_bad = 0;
    integer apply_mc, k;
    logic [7:0] v;
    initial begin
        for (int q = 0; q < 16; q++) begin st_mc[q] = 0; st_fr[q] = 0; end
        repeat (5) @(posedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(posedge MCLK);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h22, 8'h01);                 // range 1
        r14_write(7'h21, 8'd40);                 // M 40
        r14_write(7'h53, 8'd4);                  // T_PRE 4 (r32 check of the parity rule)
        cmd(8'h11);                              // START
        wait_state(ST_RUN);
        $display("RUN at frame %0d", fr);
        fast = 1;
        // ---- P1: 24 APPLYs toggling CHOP_FAST, committed at swept offsets
        for (i = 0; i < 24; i++) begin
            fast = 1 - fast;
            r14_write(7'h26, fast[7:0]);
            #((i * 1371.3) % 16000.0);
            r14_cmd(8'h33);                      // APPLY
            wait_state(ST_PRE);
            apply_mc = st_mc[ST_PRE]; tick_fr = st_fr[ST_PRE];
            wait_state(ST_PULSE);
            pre_fr = (st_mc[ST_PULSE] - apply_mc);
            wait_state(ST_RECOVER);
            pulse_fr = (afe_fall_mc - afe_rise_mc);
            $display("P1 APPLY to %s: tick in frame %2d (mod 16), PRE %0d MCLK (%0.2f frames, %0.1f us), AFE_RST high %0d MCLK (%0.1f us), rate switch %0d MCLK after the tick (%s the AFE_RST rise)",
                     fast ? "128k" : " 64k", tick_fr % 16, pre_fr, pre_fr / 32.0, pre_fr * TMCLK / 1000.0,
                     pulse_fr, pulse_fr * TMCLK / 1000.0, sw_mc - apply_mc, (sw_mc < afe_rise_mc) ? "before" : "AFTER");
            if (pre_fr * TMCLK < 20000.0 || pulse_fr * TMCLK < 100000.0 || sw_mc >= afe_rise_mc) n_bad = n_bad + 1;
            wait_state(ST_RUN);
        end
        $display("P1 done"); $finish;
        // ---- P2: APPLY_NR in ALIGN and in RUN (T_ELEC 0), at both rates
        for (k = 0; k < 8; k++) begin
            if (k == 4) begin
                r14_write(7'h26, 8'h00); cmd(8'h33); wait_state(ST_RUN);        // 64 kHz
            end
            cmd(8'h33);                          // APPLY (no change): to ALIGN through PRE..RECOVER
            wait_state(ST_ALIGN);
            #((k * 3779.1) % 200000.0);
            if (dut.seq_state === ST_ALIGN) begin
                r14_write(7'h21, 8'd40 + 8'(k % 2 ? 0 : 1));   // alternate 41 / 40
                r14_cmd(8'h44);
                wait_state(ST_FILL);
                if (ofm_mc >= st_mc[ST_ALIGN])
                    $display("P2 ALIGN (%s): OFM changed %0d MCLK (%0.2f frames) before the CIC clear (ALIGN -> FILL at the output time)",
                             dut.u_clkgen.fast ? "128k" : " 64k", st_mc[ST_FILL] - ofm_mc, (st_mc[ST_FILL] - ofm_mc) / 32.0);
            end
            wait_state(ST_RUN);
            // RUN: a step, frames to the end of its interval (the first marked output; the next 3 windows straddle)
            repeat (($urandom % 900) * 32) @(posedge MCLK);
            r14_write(7'h21, (OFM == 10'd40) ? 8'd41 : 8'd40);
            r14_cmd(8'h44);
            while (dut.cmd_valid === 1'b1) @(posedge MCLK);
            @(posedge dut.cic_stb);
            $display("P2 RUN   (%s): OFM changed %0d MCLK (%0.2f frames) before the output time that ends its interval",
                     dut.u_clkgen.fast ? "128k" : " 64k", mc - ofm_mc, (mc - ofm_mc) / 32.0);
        end
        $display("P3: %0d commands, the longest commit -> tick %0d MCLK (%0.2f frames)", nlat, max_lat, max_lat / 32.0);
        $display("P1 violations (PRE < 20 us, AFE_RST < 100 us, rate switch not before the AFE_RST rise): %0d", n_bad);
        $display("SPI errors: %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
