// audit39 C probe: the empty word's OVL copied in the cycle OVL_NOW rises (spec 3.4: OVL = OVL_NOW of the copy's
// cycle, a flag changed at that cycle's starting edge included). In IDLE (FIFO empty), four extreme codes make the
// detector hold at the e4 edge of a known frame; an empty-FIFO sample read is aimed so that its copy's cycle starts
// from 3 MCLK before to 3 MCLK after that edge in 1/4-MCLK steps; the word's OVL against OVL_NOW of the copy's cycle.
`timescale 1ns / 1ps
`default_nettype none
module tb_c39_emptyovl;
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
    integer frame_no = 0, xf0 = -100;              // frames since the release; extreme codes in frames xf0 .. xf0 + 3
    always @(posedge MCLK) if (dut.cycle == 5'd31) frame_no <= frame_no + 1;
    always @(posedge MCLK) if (dut.cycle == 5'd1)  // CODE changes at e2 (as the ADC's), taken at cycle 3
        CODE <= (frame_no + 0 >= xf0 && frame_no <= xf0 + 3) ? 5'd31 : 5'd16;
    real t_snap = 0.0, t_rise = 0.0;
    logic exp_ovl;
    always @(posedge MCLK) if (dut.smp_snap === 1'b1) begin exp_ovl = dut.ovl_now; t_snap = $realtime; end
    always @(posedge dut.ovl_now) t_rise = $realtime;
    integer nbad = 0, n_at = 0, k, f;
    real lat, t0, tgt, dt;
    logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
    initial begin
        #(200.0); RESET_N = 1'b1;
        #(2000.0);
        t0 = $realtime; r14_sample(st, sq, d, ok); lat = t_snap - t0;   // call -> the copy's edge
        for (k = -12; k <= 12; k++) begin
            while (dut.cycle != 5'd0) @(posedge MCLK);
            f = frame_no;                              // this frame
            xf0 = f + 8;                               // the 4th extreme code at cycle 3 of frame f + 11: OVL_NOW at e4
            t0 = $realtime;                            // ~ e0 of frame f
            tgt = t0 + (11 * 32 + 4) * TMCLK + TMCLK + k * TMCLK / 4.0 - lat;   // copy's cycle starts at e4 + k/4
            if (tgt > $realtime) #(tgt - $realtime);
            r14_sample(st, sq, d, ok);
            dt = (t_snap - TMCLK) - t_rise;
            if (!ok || st[SMP_VALID_LSB] !== 1'b0) $display("k %0d: not an empty word (status 0x%02h, CRC %b)", k, st, ok);
            if (st[SMP_OVL_LSB] !== exp_ovl) begin
                nbad = nbad + 1;
                $display("k %0d: copy cycle starts %0.2f MCLK from OVL_NOW's rise: empty word 0x%02h with OVL %b, OVL_NOW of the copy's cycle %b  <- differs",
                         k, dt / TMCLK, st, st[SMP_OVL_LSB], exp_ovl);
            end else
                $display("k %0d: copy cycle starts %0.2f MCLK from OVL_NOW's rise: empty word 0x%02h, OVL as OVL_NOW of the copy's cycle", k, dt / TMCLK, st);
            if (dt > -TMCLK / 2.0 && dt < TMCLK / 2.0) n_at = n_at + 1;
            repeat (40 * 32) @(posedge MCLK);          // the extremes leave the 32-frame window
        end
        $display("tb_c39_emptyovl: %0d empty words differ from OVL_NOW of their copy's cycle; %0d copies in the cycle starting at the rise", nbad, n_at);
        $finish;
    end
endmodule
`default_nettype wire
