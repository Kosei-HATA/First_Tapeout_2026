// audit 46 A probe 2: for an APPLY_NR (one DAC step) accepted in each AFE-running state before RUN (RECOVER, WAIT_E,
// ALIGN, FILL) with T_ELEC 0 and 2, the time from the step (the applying tick) to the CIC clear that starts the first
// stored window, and that this window holds no step (SEQ-06, SEQ-15; requirements 4.10 OFM row). Expected: >= T_ELEC
// ms when T_ELEC > 0 (RECOVER: >= T_ELEC after RECOVER's expiry), > 0 when T_ELEC = 0.
`timescale 1ns / 1ps
`default_nettype none
module tb_a46_nrstates;
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
    integer errors = 0;
    real t_step = -1.0, t_clear = -1.0, t_store = -1.0;
    logic [9:0] ofm_q;
    always @(posedge MCLK) begin
        #1;
        if (OFM !== ofm_q && dut.tm_rst_n) t_step = $realtime;
        ofm_q = OFM;
    end
    always @(posedge MCLK) if (dut.u_cic.step[3] && dut.u_cic.arm) t_clear = $realtime;
    always @(posedge MCLK) if (dut.seq_store && dut.seq_state == ST_FILL) t_store = $realtime;
    task automatic one(input logic [3:0] st, input logic [7:0] te, input integer m0);
        logic [7:0] v;
        r14_write(7'h51, te);
        r14_write(7'h22, 8'h04);                  // range 4, sign 0
        r14_write(7'h20, 8'(m0 >> 8)); r14_write(7'h21, 8'(m0));
        r14_cmd(8'h11);                           // START
        wait (dut.seq_state == st);
        r14_write(7'h21, 8'(m0 + 1));             // one step up
        t_step = -1.0; t_clear = -1.0; t_store = -1.0;
        r14_cmd(8'h44);                           // APPLY_NR
        wait (dut.seq_state == ST_RUN);
        @(negedge MCLK);
        r14_read(7'h06, v);
        if (t_step < 0.0) begin $display("ERROR state %0d T_ELEC %0d: APPLY_NR not applied (ERR 0x%02h)", st, te, v); errors++; end
        else begin
            $display("APPLY_NR in state %0d, T_ELEC %0d: step -> clear %0.1f us, step -> first store %0.1f us, ERR 0x%02h",
                     st, te, (t_clear - t_step) / 1000.0, (t_store - t_step) / 1000.0, v);
            if (t_clear <= t_step) begin $display("ERROR: the first stored window's clear is not after the step"); errors++; end
            if (te != 0 && st != ST_RECOVER && (t_clear - t_step) < te * 1.0e6) begin $display("ERROR: clear less than T_ELEC after the step"); errors++; end
            if (te != 0 && st == ST_RECOVER && (t_clear - t_step) < te * 1.0e6) begin $display("ERROR: (RECOVER) clear less than T_ELEC after the step"); errors++; end
        end
        r14_cmd(8'h22);
        wait (dut.seq_state == ST_IDLE);
        r14_write(7'h06, 8'hFF);
        #(5000.0);
    endtask
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h50, 8'd5);
        one(ST_RECOVER, 8'd0, 300); one(ST_RECOVER, 8'd2, 301);
        one(ST_WAIT_E, 8'd2, 302);
        one(ST_ALIGN, 8'd0, 303);   one(ST_ALIGN, 8'd2, 304);
        one(ST_FILL, 8'd0, 305);    one(ST_FILL, 8'd2, 306);
        $display("tb_a46_nrstates done: errors %0d, SPI errors %0d", errors, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
