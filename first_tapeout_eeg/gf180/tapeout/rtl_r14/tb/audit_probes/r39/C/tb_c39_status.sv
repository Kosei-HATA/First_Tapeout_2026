// audit39 C probe: the header STATUS copied in the cycle a STOP's tick changes READY (1 -> 0) and AFE_RST (0 -> 1).
// Spec 3.2: STATUS is the value of the copy's cycle (cs_start), a flag changed at that cycle's starting edge included.
// A STATUS read is aimed in 1/4-MCLK steps from 3 MCLK before to 3 MCLK after the e25 edge of the tick that takes a
// pending STOP in RUN; per read: the header's READY and AFE_RST against (state == RUN) and AFE_RST of the copy's cycle.
`timescale 1ns / 1ps
`default_nettype none
module tb_c39_status;
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
    // the registers of the copy's cycle
    real t_cs = 0.0, t_tick_edge = 0.0;
    logic exp_ready, exp_afe;
    always @(posedge MCLK) begin
        if (dut.u_spi.cs_start === 1'b1) begin
            exp_ready = (dut.seq_state === 4'd6);
            exp_afe   = dut.seq_afe_rst;
            t_cs      = $realtime;                    // the copy's edge (the end of the copy's cycle)
        end
    end
    logic [3:0] st_prev = 4'd0;
    always @(dut.seq_state) begin
        if (st_prev === 4'd6 && dut.seq_state === 4'd0) t_tick_edge = $realtime;   // RUN -> IDLE: the STOP's e25
        st_prev = dut.seq_state;
    end
    integer nbad = 0, n_at = 0, k;
    real lat, t0, tgt, dt;
    logic [7:0] v;
    initial begin
        #(200.0); RESET_N = 1'b1;
        #(2000.0);
        r14_read(7'h03, v);                            // latency of the copy edge from the call
        t0 = $realtime; r14_read(7'h03, v); lat = t_cs - t0;
        for (k = -12; k <= 12; k++) begin
            r14_cmd(8'h11);                            // START
            while (dut.seq_state !== 4'd6) @(posedge MCLK);
            repeat (2000) @(posedge MCLK);
            @(posedge dut.u_clkgen.tick);              // a tick (cycle 24 starts); the next is 256 MCLK on
            t0 = $realtime;
            r14_cmd(8'h22);                            // STOP: pending to the next tick
            // the write outlasts one 128 kHz tick period: the STOP is taken at the second tick (512 MCLK on). Aim the
            // copy's edge at that tick's e25 + 1 MCLK + k/4 MCLK (the copy's cycle then starts at e25 + k/4 MCLK)
            tgt = t0 + 512.0 * TMCLK + TMCLK + k * TMCLK / 4.0 - lat;
            if (tgt > $realtime) #(tgt - $realtime);
            r14_read(7'h03, v);
            while (dut.seq_state !== 4'd0) @(posedge MCLK);
            dt = (t_cs - TMCLK) - t_tick_edge;           // the copy cycle's start against the STOP's e25
            if (spi_status[STATUS_READY_LSB] !== exp_ready || spi_status[STATUS_AFE_RST_LSB] !== exp_afe) begin
                nbad = nbad + 1;
                $display("k %0d: copy cycle starts %0.2f MCLK from e25: header STATUS 0x%02h (READY %b AFE_RST %b), registers of the copy's cycle READY %b AFE_RST %b  <- differs",
                         k, dt / TMCLK, spi_status, spi_status[STATUS_READY_LSB], spi_status[STATUS_AFE_RST_LSB], exp_ready, exp_afe);
            end else
                $display("k %0d: copy cycle starts %0.2f MCLK from e25: header STATUS 0x%02h, as the registers", k, dt / TMCLK, spi_status);
            if (dt > -TMCLK / 2.0 && dt < TMCLK / 2.0) n_at = n_at + 1;
            r14_write(7'h06, 8'hFF);
        end
        $display("tb_c39_status: %0d reads differ from the registers of their copy's cycle; %0d copies in the cycle starting at e25", nbad, n_at);
        $finish;
    end
endmodule
`default_nettype wire
