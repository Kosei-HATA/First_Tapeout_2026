// tb_a30_restore - audit round 30 (A). A test setting used in RUN (TEST_CTRL = 0x02, CHOP_STOP, applied by APPLY),
// then "restored" with step 3's bracket as REG-08 / step 3 say (write the reset value, read back twice, lock, check the
// lock by TEST_CTRL's ADDR_ERR). What do the pins and the samples do afterwards, and what does the next tracking
// APPLY_NR get?
`timescale 1ns / 1ps
`default_nettype none
module tb_a30_restore;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd14 + 5'($urandom % 4);   // mid-scale codes
    logic [7:0] v, v2, s8; logic [15:0] q; logic [23:0] d; bit ok; integer i, nchg;
    task automatic bracket(input logic [7:0] tc);
        r14_write(7'h11, 8'h3C); r14_read(7'h06, v); if (v !== 8'h00) $display("  (1) ERR 0x%02h", v);
        r14_write(7'h61, tc);
        r14_read(7'h61, v); r14_read(7'h61, v2); $display("  (3) TEST_CTRL 0x%02h 0x%02h", v, v2);
        r14_write(7'h11, 8'h00);
        r14_write(7'h61, 8'h00); r14_read(7'h06, v); $display("  (5) ERR 0x%02h (0x08: locked)", v);
        r14_write(7'h06, v);
    endtask
    task automatic read_all(input string tag);
        nchg = 0;
        for (i = 0; i < 4; i++) begin
            @(negedge DRDY_N); #(2000.0);
            r14_sample(s8, q, d, ok);
            if (s8[SMP_CHANGED_LSB] || s8[SMP_OVL_LSB]) nchg++;
        end
        $display("%s: 4 samples (CRC %b), %0d with CHANGED/OVL; CHOP_EN pin %b, TEST_CTRL active 0x%02h, STATE %0d", tag,
                 ok, nchg, CHOP_EN, {6'd0, dut.a_cstop, dut.a_azero}, dut.seq_state);
    endtask
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_read(7'h06, v); r14_write(7'h06, v);
        r14_cmd(CMD_START);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        read_all("RUN, normal");
        $display("bracket: set TEST_CTRL = 0x02 (CHOP_STOP), then APPLY");
        bracket(8'h02);
        r14_cmd(CMD_APPLY);
        while (dut.u_seq.state !== ST_PRE) @(posedge MCLK);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        read_all("RUN, test applied");
        $display("bracket: restore TEST_CTRL = 0x00 (REG-08: 'use the bracket to return to the reset values')");
        bracket(8'h00);
        r14_read(7'h61, v); r14_read(7'h71, v2);
        $display("TEST_CTRL shadow 0x%02h, active copy 0x%02h", v, v2);
        read_all("RUN, after the restore");
        $display("tracking APPLY_NR (M unchanged)");
        r14_read(7'h06, v); r14_write(7'h06, v);
        r14_cmd(CMD_APPLY_NR); #(40000.0);
        r14_read(7'h06, v);
        $display("ERR after APPLY_NR 0x%02h, CHOP_EN %b", v, CHOP_EN);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
