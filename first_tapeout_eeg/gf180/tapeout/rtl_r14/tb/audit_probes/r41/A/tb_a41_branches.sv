// audit 41 A probe: the sequencer branches that tb_top_r14's trace never takes at the block level (its "not covered"
// list), driven through the pins: STOP in ALIGN (no CIC clear at the next output time) and in FILL (no store), FLUSH in
// WARMUP, PRE and PULSE (no state change, the waits unchanged), START refused in RECOVER, WAIT_E, ALIGN, FILL, PRE and
// PULSE (STATE_ERR only), APPLY with an inconsistent shadow in WAIT_E / RECOVER (CFG_ERR only), APPLY_NR beyond one step
// in ALIGN (CFG_ERR only). Every refused command: state unchanged, pins unchanged, ERR exactly the flag.
`timescale 1ns / 1ps
`default_nettype none
module tb_a41_branches;
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
    integer errors = 0, ncase = 0, seed = 41;
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd12 + 5'($urandom(seed) % 8);
    task automatic err(input string m);
        errors = errors + 1;
        if (errors <= 30) $display("ERROR @%0t ns: %s", $time / 1000, m);
    endtask
    task automatic wait_state(input logic [3:0] s, input integer max_us);
        integer t;
        t = 0;
        while (dut.seq_state !== s && t < max_us * 10) begin #100.0; t = t + 1; end
        if (dut.seq_state !== s) err($sformatf("state %0d not reached within %0d us (state %0d)", s, max_us, dut.seq_state));
    endtask
    task automatic clr_err;
        logic [7:0] v;
        r14_read(7'h06, v);
        if (v != 8'h00) r14_write(7'h06, v);
    endtask
    task automatic expect_err(input logic [7:0] want, input string tag);
        logic [7:0] v;
        r14_read(7'h06, v);
        if (v !== want) err($sformatf("%s: ERR 0x%02h, expected 0x%02h", tag, v, want));
        if (v != 8'h00) r14_write(7'h06, v);
    endtask
    // a refused command: wait for its tick, then the state and every apply pin as before, ERR exactly the flag
    task automatic refused(input logic [7:0] code, input logic [7:0] flag, input string tag);
        logic [3:0] s0; logic [9:0] m0; logic [3:0] e0, c0; logic a0;
        s0 = dut.seq_state; m0 = OFM; e0 = OFEN; c0 = CPF_TRIM; a0 = AFE_RST;
        r14_cmd(code);
        wait (dut.u_regs.pend == 1'b0);
        @(negedge MCLK);
        if (dut.seq_state !== s0) err($sformatf("%s: state %0d -> %0d", tag, s0, dut.seq_state));
        if (OFM !== m0 || OFEN !== e0 || CPF_TRIM !== c0 || AFE_RST !== a0) err($sformatf("%s: a pin changed", tag));
        expect_err(flag, tag);
        ncase = ncase + 1;
    endtask
    integer t0, i;
    logic [2:0] nstb0;
    logic [15:0] seq0;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;              // CRC on
        r14_write(7'h09, 8'h00);                                 // ALERT_MASK_D 0 (host step 3)
        clr_err; expect_err(8'h00, "start");
        // ---- A: STOP in ALIGN (retry until ALIGN has >= ~150 frames left before its output time)
        for (i = 0; i < 6; i = i + 1) begin
            r14_cmd(CMD_START);
            wait_state(ST_ALIGN, 9000);
            if (dut.u_cic.dcnt < 10'd850) begin
                nstb0 = dut.u_cic.nstb;
                r14_cmd(CMD_STOP);
                wait (dut.u_regs.pend == 1'b0);
                @(negedge MCLK);
                if (dut.seq_state !== ST_IDLE || AFE_RST !== 1'b1) err("A: STOP in ALIGN did not lead to IDLE with AFE_RST 1");
                seq0 = dut.seq_cnt;
                wait (dut.seq_cnt == seq0 + 16'd2); @(negedge MCLK);
                if (dut.u_cic.nstb !== nstb0 || nstb0 !== 3'd3)
                    err($sformatf("A: the CIC cleared after a STOP in ALIGN (nstb %0d -> %0d)", nstb0, dut.u_cic.nstb));
                if (dut.u_fifo.level !== 4'd0) err("A: a sample stored after a STOP in ALIGN");
                expect_err(8'h00, "A STOP in ALIGN");
                $display("A  STOP in ALIGN %0d frames before its output time: IDLE, no clear (nstb %0d), no store",
                         1023 - dut.u_cic.dcnt, dut.u_cic.nstb);
                ncase = ncase + 1;
                break;
            end
            wait_state(ST_FILL, 2000);
            r14_cmd(CMD_STOP);
            wait (dut.u_regs.pend == 1'b0); @(negedge MCLK);
            clr_err;
        end
        // ---- B: STOP in FILL: IDLE, no store at the third output after the clear
        r14_cmd(CMD_START);
        wait_state(ST_FILL, 9000);
        r14_cmd(CMD_STOP);
        wait (dut.u_regs.pend == 1'b0); @(negedge MCLK);
        if (dut.seq_state !== ST_IDLE || AFE_RST !== 1'b1) err("B: STOP in FILL did not lead to IDLE with AFE_RST 1");
        seq0 = dut.seq_cnt;
        wait (dut.seq_cnt == seq0 + 16'd4); @(negedge MCLK);
        if (dut.u_fifo.level !== 4'd0 || DRDY_N !== 1'b1) err("B: a sample stored after a STOP in FILL");
        expect_err(8'h00, "B STOP in FILL");
        $display("B  STOP in FILL: IDLE, no store over 4 output times");
        ncase = ncase + 1;
        // ---- C: FLUSH in WARMUP; START refused in WARMUP is covered by tb_top_r14 (E); RECOVER: START refused,
        //      APPLY with M beyond the range: CFG_ERR
        r14_write(7'h51, 8'h01);                                 // T_ELEC 1 ms (written in IDLE)
        r14_cmd(CMD_START);
        wait_state(ST_WARMUP, 100);
        t0 = $time / 1000;
        r14_cmd(CMD_FLUSH);
        wait (dut.u_regs.pend == 1'b0); @(negedge MCLK);
        if (dut.seq_state !== ST_WARMUP) err("C: FLUSH moved WARMUP");
        expect_err(8'h00, "C FLUSH in WARMUP");
        wait_state(ST_RECOVER, 6000);
        if (($time / 1000) - t0 > 5020 || ($time / 1000) - t0 < 4950)
            err($sformatf("C: WARMUP lasted %0d us after the FLUSH (5000 expected from the START)", ($time / 1000) - t0));
        refused(CMD_START, 8'h40, "C START in RECOVER");
        r14_write(7'h22, 8'h01); r14_write(7'h20, 8'h01);       // range 1 with M 256: inconsistent shadow
        refused(CMD_APPLY, 8'h20, "C APPLY (M beyond range 1) in RECOVER");
        wait_state(ST_WAIT_E, 400);
        refused(CMD_START, 8'h40, "C START in WAIT_E");
        refused(CMD_APPLY, 8'h20, "C APPLY (M beyond range 1) in WAIT_E");
        refused(CMD_FLUSH, 8'h00, "C FLUSH in WAIT_E");
        r14_write(7'h20, 8'h00); r14_write(7'h21, 8'h05);       // range 1, M 5: consistent, five steps from M 0
        wait_state(ST_ALIGN, 1200);
        if (dut.u_cic.dcnt < 10'd900) begin
            refused(CMD_APPLY_NR, 8'h20, "C APPLY_NR beyond one step in ALIGN");
        end
        wait_state(ST_FILL, 1100);
        refused(CMD_START, 8'h40, "C START in FILL");
        refused(CMD_APPLY_NR, 8'h20, "C APPLY_NR beyond one step in FILL");
        refused(CMD_FLUSH, 8'h00, "C FLUSH in FILL");
        wait_state(ST_RUN, 3200);
        // ---- D: APPLY in RUN (range 1, M 5), then FLUSH and START in PRE and PULSE (T_PRE 20 = 156 us and T_RST 40 =
        //      312 us, written in RUN, so that each refused command's tick falls inside the wait it is meant for)
        r14_write(7'h53, 8'd20); r14_write(7'h54, 8'd40);
        expect_err(8'h00, "D timer writes in RUN");
        r14_cmd(CMD_APPLY);
        wait_state(ST_PRE, 50);
        t0 = $time;
        refused(CMD_FLUSH, 8'h00, "D FLUSH in PRE");
        wait_state(ST_PULSE, 300);
        refused(CMD_START, 8'h40, "D START in PULSE");
        refused(CMD_FLUSH, 8'h00, "D FLUSH in PULSE");
        refused(CMD_APPLY_NR, 8'h40, "D APPLY_NR in PULSE");
        wait_state(ST_RECOVER, 600);
        if (dut.u_regs.a_m !== 10'd5 || OFM !== 10'd5 || OFEN !== 4'b0001) err("D: the APPLY did not apply range 1, M 5");
        $display("D  PRE / PULSE: FLUSH, START, APPLY_NR refused or ignored as the table gives; PRE + PULSE %0.1f us",
                 ($time - t0) / 1000.0);
        r14_cmd(CMD_STOP); wait (dut.u_regs.pend == 1'b0);
        $display("tb_a41_branches: %0d refused / ignored cases checked, %0d errors, SPI errors %0d", ncase, errors, spi_errors);
        if (errors == 0 && spi_errors == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
    initial begin #(200_000_000.0); $display("FAIL: watchdog"); $finish; end
endmodule
`default_nettype wire
