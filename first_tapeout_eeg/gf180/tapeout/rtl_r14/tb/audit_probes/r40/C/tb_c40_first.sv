// audit40 C probe: the status byte of the first sample of a run (FILL's store) while flags stand (spec 3.4: OVERRUN =
// DFLAG.OVERRUN and ERR = ALERT of the store's cycle; DAT-02, FLG-03), and of a RUN sample with only RESET_FLAG as
// the ALERT source. (1) RUN, the FIFO left to overflow (DFLAG.OVERRUN), APPLY in RUN, the first sample after it;
// (2) STOP, START with DFLAG standing, the first sample; (3) DFLAG cleared, a SOFT_RESET (RESET_FLAG, ALERT_MASK 0xFF),
// START, a RUN sample. Each sample's status against the registers of its store's cycle.
`timescale 1ns / 1ps
`default_nettype none
module tb_c40_first;
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
    logic ovl_force = 1'b0;
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= ovl_force ? 5'd31 : 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"
    // the flags of every store's cycle, by SEQ
    logic [7:0] exp_st [0:65535];
    logic       is_fill [0:65535];
    always @(posedge MCLK) if (dut.push_ok === 1'b1) begin
        exp_st[dut.seq_cnt] = 8'h00;
        exp_st[dut.seq_cnt][SMP_VALID_LSB]   = 1'b1;
        exp_st[dut.seq_cnt][SMP_OVERRUN_LSB] = dut.u_regs.dflag[0];
        exp_st[dut.seq_cnt][SMP_ERR_LSB]     = (|(dut.u_regs.err & dut.u_regs.r_mask)) |
                                               (|(dut.u_regs.dflag_byte & dut.u_regs.mask_d_byte));
        is_fill[dut.seq_cnt] = (dut.seq_state === 4'd5);
    end
    integer nbad = 0;
    task automatic first_sample(input string what);
        logic [7:0] st, m; logic [15:0] sq; logic [23:0] d; bit ok;
        while (dut.seq_state !== 4'd6) @(posedge MCLK);
        while (DRDY_N !== 1'b0) @(posedge MCLK);
        r14_sample(st, sq, d, ok);
        m = (1 << SMP_VALID_LSB) | (1 << SMP_OVERRUN_LSB) | (1 << SMP_ERR_LSB);
        if (!ok || (st & m) !== (exp_st[sq] & m)) nbad = nbad + 1;
        $display("%s: SEQ %0d (%s store) status 0x%02h, the store's cycle gives VALID/OVERRUN/ERR 0x%02h, CRC %b%s",
                 what, sq, is_fill[sq] ? "FILL's" : "a RUN", st, exp_st[sq] & m, ok,
                 (!ok || (st & m) !== (exp_st[sq] & m)) ? "  <- differs" : "");
    endtask
    logic [7:0] v;
    initial begin
        #(200.0); RESET_N = 1'b1;
        #(2000.0);
        r14_write(7'h06, 8'hFF);                         // ERR cleared (RESET_FLAG)
        r14_cmd(8'h11);                                  // START
        while (dut.seq_state !== 4'd6) @(posedge MCLK);
        repeat (11 * 32768) @(posedge MCLK);             // no reads: the 8-deep FIFO overflows
        r14_read(7'h07, v); $display("DFLAG 0x%02h before the APPLY", v);
        r14_cmd(8'h33);                                  // (1) APPLY in RUN, DFLAG.OVERRUN standing
        while (dut.seq_state === 4'd6) @(posedge MCLK);  // the APPLY's tick (the FIFO is flushed)
        first_sample("(1) the first sample after an APPLY in RUN");
        r14_cmd(8'h22);                                  // (2) STOP, then START with DFLAG standing
        while (dut.seq_state !== 4'd0) @(posedge MCLK);
        repeat (2000) @(posedge MCLK);
        r14_read(7'h07, v); $display("DFLAG 0x%02h before the START", v);
        r14_cmd(8'h11);
        while (dut.seq_state === 4'd0) @(posedge MCLK);
        first_sample("(2) the first sample after a START");
        r14_cmd(8'h22);
        while (dut.seq_state !== 4'd0) @(posedge MCLK);
        r14_write(7'h07, 8'hFF);                         // (3) DFLAG cleared; RESET_FLAG by a SOFT_RESET
        r14_cmd(8'hA5);
        #(2000.0);
        r14_read(7'h06, v); $display("ERR 0x%02h before the START (ALERT_MASK at its reset value 0xFF)", v);
        r14_cmd(8'h11);
        while (dut.seq_state === 4'd0) @(posedge MCLK);
        first_sample("(3) the first sample with RESET_FLAG standing");
        first_sample("(3) the second sample with RESET_FLAG standing");
        // (4) the host's setting (step 3): ALERT_MASK_D 0x00, ERR and DFLAG cleared; an overload in RUN sets DFLAG.OVL;
        // the samples' ERR (ALERT at the store) must stay 0, OVL marks three of them
        r14_cmd(8'h22);
        while (dut.seq_state !== 4'd0) @(posedge MCLK);
        r14_write(7'h09, 8'h00);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        r14_cmd(8'h11);
        while (dut.seq_state !== 4'd6) @(posedge MCLK);
        while (DRDY_N === 1'b0) begin logic [7:0] s_; logic [15:0] q_; logic [23:0] d_; bit o_; r14_sample(s_, q_, d_, o_); end
        ovl_force = 1'b1; repeat (40 * 32) @(posedge MCLK); ovl_force = 1'b0;
        r14_read(7'h07, v); $display("DFLAG 0x%02h after the overload (ALERT_MASK_D 0x00)", v);
        for (int i = 0; i < 4; i++) first_sample("(4) a sample after an overload, ALERT_MASK_D 0x00");
        $display("tb_c40_first: %0d samples differ from the flags of their store's cycle (spi errors %0d)", nbad, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
