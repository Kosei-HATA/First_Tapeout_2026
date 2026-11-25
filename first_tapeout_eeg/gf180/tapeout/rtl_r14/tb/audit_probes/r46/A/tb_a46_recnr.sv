// audit 46 A probe: an APPLY_NR accepted in RECOVER (T_ELEC > 0 at its tick); T_ELEC then written (CMD_PENDING 0, so
// not guarded) before RECOVER's expiry. Which T_ELEC decides the electrode wait after that offset step?
// Requirements 5.4 step 4 / spec 2.3: "tick で読むのは START の T_WARM、APPLY の T_PRE、APPLY_NR の T_ELEC、..."
`timescale 1ns / 1ps
`default_nettype none
module tb_a46_recnr;
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

    // state log
    logic [3:0] st_q = 4'd0;
    real t_nr = 0.0;
    always @(posedge MCLK) begin
        if (dut.seq_state != st_q) $display("  %0.3f us: state %0d -> %0d", $realtime / 1000.0, st_q, dut.seq_state);
        st_q <= dut.seq_state;
        if (dut.u_seq.apply && dut.seq_state == ST_RECOVER) begin t_nr = $realtime; $display("  %0.3f us: APPLY_NR applied in RECOVER, t_elec at its tick = %0d", $realtime / 1000.0, dut.t_elec); end
    end
    logic [7:0] v;
    task automatic run_case(input logic [7:0] te_cmd, input logic [7:0] te_after);
        real t_align;
        $display("case: T_ELEC %0d at the APPLY_NR's tick, %0d written after it (in RECOVER)", te_cmd, te_after);
        r14_write(7'h51, te_cmd);
        r14_cmd(8'h11);                                       // START
        wait (dut.seq_state == ST_RECOVER);
        r14_cmd(8'h44);                                       // APPLY_NR, no change (nr_ok)
        wait (dut.u_regs.pend == 1'b0);
        @(negedge MCLK);
        if (dut.seq_state != ST_RECOVER) $display("  ERROR: left RECOVER before the write");
        r14_write(7'h51, te_after);                           // CMD_PENDING 0: accepted
        r14_read(7'h06, v);
        $display("  ERR after the write 0x%02h (state %0d)", v, dut.seq_state);
        wait (dut.seq_state == ST_ALIGN);
        t_align = $realtime;
        $display("  ALIGN reached %0.3f us after the APPLY_NR's step", (t_align - t_nr) / 1000.0);
        r14_cmd(8'h22);                                       // STOP
        wait (dut.seq_state == ST_IDLE);
        r14_write(7'h06, 8'hFF);
        #(20000.0);
    endtask
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        run_case(8'd2, 8'd0);
        run_case(8'd0, 8'd3);
        $display("tb_a46_recnr done, SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
