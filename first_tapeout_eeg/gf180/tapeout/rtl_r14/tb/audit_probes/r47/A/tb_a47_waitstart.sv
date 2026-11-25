// audit 47 A probe: when does an in-progress APPLY (RUN -> PRE -> PULSE -> RECOVER) read T_RST and T_REC?
// T_RST written in PRE and T_REC written in PULSE (no command pending, so not guarded) must set PULSE's and
// RECOVER's lengths if they are read at PRE's and PULSE's expiry (not at WARMUP's or RECOVER's).
`timescale 1ns / 1ps
`default_nettype none
module tb_a47_waitstart;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd12 + 5'($urandom % 8);
    real t_pre_in, t_pulse_in, t_rec_in, t_rec_out;
    logic [3:0] st_q = 4'd0;
    always @(posedge MCLK) begin
        #0.1;
        if (dut.seq_state !== st_q) begin
            if (dut.seq_state == ST_PRE)     t_pre_in   = $realtime;
            if (dut.seq_state == ST_PULSE)   t_pulse_in = $realtime;
            if (dut.seq_state == ST_RECOVER) t_rec_in   = $realtime;
            if (st_q == ST_RECOVER)          t_rec_out  = $realtime;
        end
        st_q = dut.seq_state;
    end
    logic [7:0] v;
    integer errs = 0;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        #2000;
        r14_write(7'h06, 8'hFF);                         // clear RESET_FLAG
        r14_write(7'h53, 8'd20);                         // T_PRE 20 (156.25 us): time to write inside PRE
        r14_cmd(8'h11);                                  // START (defaults: T_WARM 5, T_REC 32, T_RST 13)
        wait (dut.seq_state == ST_RUN);
        $display("RUN at %0.1f us", $realtime / 1000.0);
        r14_cmd(8'h33);                                  // APPLY in RUN
        wait (dut.seq_state == ST_PRE);
        #1000;
        r14_write(7'h54, 8'd40);                         // T_RST 40 in PRE (312.5 us)
        r14_read(7'h06, v);
        $display("ERR after the T_RST write in PRE: 0x%02h (STATE %0d)", v, dut.seq_state);
        wait (dut.seq_state == ST_PULSE);
        #1000;
        r14_write(7'h52, 8'd100);                        // T_REC 100 in PULSE (781.25 us)
        r14_read(7'h06, v);
        $display("ERR after the T_REC write in PULSE: 0x%02h (STATE %0d)", v, dut.seq_state);
        wait (st_q == ST_RECOVER && dut.seq_state != ST_RECOVER);
        #100;
        $display("PRE %0.2f us, PULSE %0.2f us (T_RST 40 -> 312.50), RECOVER %0.2f us (T_REC 100 -> 781.25)",
                 (t_pulse_in - t_pre_in) / 1000.0, (t_rec_in - t_pulse_in) / 1000.0, (t_rec_out - t_rec_in) / 1000.0);
        if ((t_rec_in - t_pulse_in) / 1000.0 < 312.0 || (t_rec_out - t_rec_in) / 1000.0 < 781.0) errs++;
        $display("%s: T_RST read at PRE's expiry, T_REC at PULSE's expiry", errs ? "NOT CONFIRMED" : "CONFIRMED");
        $finish;
    end
endmodule
`default_nettype wire
