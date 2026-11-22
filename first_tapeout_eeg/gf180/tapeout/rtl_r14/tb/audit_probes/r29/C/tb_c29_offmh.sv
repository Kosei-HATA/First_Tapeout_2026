// Audit round 29 (C): OFF_M_H written with the test key locked (as host steps 3 and 7 do): the value and ERR after it
`timescale 1ns / 1ps
module tb_c29_offmh;
    logic clk = 0, rst_n = 0; logic [6:0] addr = 0; logic we = 0; logic [7:0] wdata = 0;
    logic frame_err_set = 0, crc_err_set = 0, addr_err_set = 0; logic [3:0] state = 0; logic afe_rst = 1, fifo_nonempty = 0;
    logic [3:0] fifo_level = 0; logic ovl_now = 0, ovr_set = 0, ovl_set = 0, seq_state_err = 0, seq_cfg_err = 0, cmd_ack = 0, apply = 0;
    wire [7:0] rdata, cmd_code, status_byte, t_warm, t_elec, t_rec, t_pre, t_rst;
    wire addr_ok, cmd_valid, soft_reset, cfg_ok, nr_ok, off_sign, chop_fast, dwa_en, atp_en, chop_stop, adc_zero, raw_en, crc_en,
         drdy_mode, alert, dflag_overrun;
    wire [9:0] off_mag; wire [3:0] ofen, cpf_trim, blank_len, atp_sel; wire [1:0] afe_ibias, btrim_p, btrim_n, dbg_sel;
    wire [2:0] chop1_rate;
    eeg_regs #(.FIFO_DEPTH(8)) dut (.*);
    always #15.26 clk = ~clk;
    task automatic wr(input logic [6:0] a, input logic [7:0] d);
        @(negedge clk); addr = a; we = 1; wdata = d; @(negedge clk); we = 0;
    endtask
    initial begin
        repeat (3) @(negedge clk); rst_n = 1;
        wr(7'h06, 8'hFF);                                   // ERR cleared (RESET_FLAG)
        wr(7'h20, 8'h02);                                   // OFF_M_H = 2 (M 512..767), key locked
        @(negedge clk); addr = 7'h20; #1 $display("key locked: OFF_M_H reads 0x%02h, ERR 0x%02h", rdata, dut.err);
        $finish;
    end
endmodule
