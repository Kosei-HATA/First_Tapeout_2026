// audit 47 A probe 2: a timer write during a wait never changes that wait (each wait loads its timer at its start):
// T_PRE written in PRE, T_RST written in PULSE and T_ELEC written in WAIT_E, all accepted without a flag.
`timescale 1ns / 1ps
`default_nettype none
module tb_a47_inprog;
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
    real t_in [0:8];
    real t_len [0:8];
    logic [3:0] st_q = 4'd0;
    always @(posedge MCLK) begin
        #0.1;
        if (dut.seq_state !== st_q) begin
            if (st_q <= 8) t_len[st_q] = $realtime - t_in[st_q];
            if (dut.seq_state <= 8) t_in[dut.seq_state] = $realtime;
        end
        st_q = dut.seq_state;
    end
    logic [7:0] v, e1, e2, e3;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        #2000;
        r14_write(7'h06, 8'hFF);
        r14_write(7'h53, 8'd20);                          // T_PRE 20 (156.25 us)
        r14_write(7'h51, 8'd3);                           // T_ELEC 3 ms
        r14_cmd(8'h11);                                   // START
        wait (dut.seq_state == ST_RUN);
        r14_cmd(8'h33);                                   // APPLY in RUN
        wait (dut.seq_state == ST_PRE);   #1000; r14_write(7'h53, 8'd3);    r14_read(7'h06, e1);  // T_PRE 3 in PRE
        wait (dut.seq_state == ST_PULSE); #1000; r14_write(7'h54, 8'd60);   r14_read(7'h06, e2);  // T_RST 60 in PULSE
        wait (dut.seq_state == ST_WAIT_E); #1000; r14_write(7'h51, 8'd1);   r14_read(7'h06, e3);  // T_ELEC 1 in WAIT_E
        wait (dut.seq_state == ST_ALIGN);
        #100;
        $display("ERR after each write: 0x%02h 0x%02h 0x%02h", e1, e2, e3);
        $display("PRE %0.2f us (T_PRE 20 at its start; 3 written inside), PULSE %0.2f us (T_RST 13 at its start; 60 written inside), WAIT_E %0.3f ms (T_ELEC 3 at its start; 1 written inside)",
                 t_len[ST_PRE] / 1000.0, t_len[ST_PULSE] / 1000.0, t_len[ST_WAIT_E] / 1e6);
        $finish;
    end
endmodule
`default_nettype wire
