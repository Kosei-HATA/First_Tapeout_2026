// audit41 C probe: the copy instant of a register read's data byte. A STATE (0x04) read is aimed so that the data
// byte's load (the synchronized SCLK fall after the header) falls around e25 of the tick that takes a pending START
// (IDLE -> WARMUP) or STOP (WARMUP -> IDLE), the frame start moved in 1/4-MCLK steps. Per trial: the load edge
// relative to the state's change edge, the data byte read, and the state in the load cycle.
`timescale 1ns / 1ps
`default_nettype none
module tb_c41_rdinstant;
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
    realtime t_load, t_chg;
    logic [3:0] st_load, st_prev;
    bit got_load = 1'b0;
    always @(negedge CS_N) got_load = 1'b0;
    always @(posedge MCLK) begin
        if (dut.u_spi.sclk_fall && dut.u_spi.bit_cnt == 3'd0 && dut.u_spi.st == 4'd2 && !got_load) begin
            got_load = 1'b1;
            t_load = $realtime; st_load = dut.seq_state;      // the edge ending the load cycle; the cycle's state
        end
    end
    always @(dut.seq_state) t_chg = $realtime;              // the state's change edge
    always @(posedge MCLK) if (dut.u_seq.state != dut.u_seq.nxt) $display("  change %0d -> %0d at %0t", dut.u_seq.state, dut.u_seq.nxt, $realtime);
    integer n_late;
    initial begin
        logic [7:0] v;
        real d, rel;
        realtime ta, t0;
        n_late = 0;
        #(10 * TMCLK); RESET_N = 1'b1; #(300 * TMCLK);
        spi_tidle = 125.0;
        for (int k = 0; k < 50; k++) begin
            @(posedge dut.u_clkgen.tick);                    // e24 of a tick, ta
            ta = $realtime;
            r14_cmd((k % 2 == 0) ? 8'h11 : 8'h22);           // START, then STOP: pending before the second tick after
            d = -3.0 + 0.25 * (k % 25);
            // the second tick after ta takes it: its e25 = ta + 2 * 256 MCLK + 1 MCLK; the data byte's SCLK fall is
            // 4,050 ns after CS_N's fall, and its synchronized load about 2.5 MCLK later
            t0 = ta + (2 * 256 + 1) * TMCLK + d * TMCLK - 4050.0 - 2.5 * TMCLK;
            if ($realtime > t0) begin $display("late for trial %0d", k); n_late++; continue; end
            #(t0 - $realtime);
            r14_read(7'h04, v);
            rel = (t_load - t_chg) / TMCLK;
            $display("trial %0d %s d %5.2f: load at %0t, load edge %5.2f MCLK after the change edge, STATE read 0x%02h, state in the load cycle %0d",
                     k, (k % 2 == 0) ? "START" : "STOP ", d, t_load, rel, v, st_load);
            if (k % 2 == 0) wait (dut.seq_state === 4'd1); else wait (dut.seq_state === 4'd0);
            #(2000.0);
        end
        $display("done (%0d late)", n_late);
        $finish;
    end
endmodule
`default_nettype wire
