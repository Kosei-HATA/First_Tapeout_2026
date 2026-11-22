// tb_c35_flags (audit 35, C): three directed checks through the pins (SPI), each against the specification:
//   R  RESET_FLAG (ERR bit 0, W1C only: REG-02, FLG-02) is still set after an accepted START (no W1C written)
//   D  DFLAG.OVERRUN (W1C only: REG-02) is still set after an accepted APPLY in RUN, and STATUS.ALERT with it
//   E  the empty word's ERR bit is ALERT at the header's copy (spec 3.2, 3.4: "その時点の ALERT"): FRAME_ERR is
//      forced in the cycle before the copy, so ALERT rises at the edge that starts the copy's cycle
`timescale 1ns / 1ps
`default_nettype none
module tb_c35_flags;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd10 + ($urandom % 12);   // in-range codes
    `include "spi_bfm_r14.svh"
    integer errors = 0;
    logic [7:0] v, st;
    logic [15:0] sq;
    logic [23:0] d;
    bit ok;
    bit arm_e = 1'b0;
    integer n_forced = 0;
    // E: the cycle before the copy of a sample read's header (0xC0): seven bits in, the eighth SCLK rise entering
    // the synchronizer (it is detected in the next cycle, which takes the copy)
    always @(negedge MCLK) begin
        if (arm_e && dut.u_spi.st == 4'd1 && dut.u_spi.bit_cnt == 3'd7 && dut.u_spi.rx_sh == 7'h60 &&
            dut.u_spi.sclk_q[1:0] == 2'b01 && dut.u_spi.cs_act) begin
            force dut.u_spi.frame_err = 1'b1;
            n_forced++;
            arm_e = 1'b0;
            @(negedge MCLK);
            release dut.u_spi.frame_err;
            if (dut.smp_snap !== 1'b1) $display("E SETUP: no copy in the cycle after the forced FRAME_ERR");
        end
    end
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (200) @(posedge MCLK);
        // ---------------- R
        r14_read(7'h06, v);
        $display("R: ERR 0x%02h after RESET_N (RESET_FLAG 1 expected)", v);
        r14_cmd(8'h11);                                 // START with the reset values (range 0: accepted)
        while (dut.seq_state !== 4'd1) @(posedge MCLK);
        repeat (2000) @(posedge MCLK);
        r14_read(7'h06, v);
        if (v !== 8'h01) begin errors++; $display("R FAIL: ERR 0x%02h after an accepted START, expected 0x01 (RESET_FLAG is W1C only: REG-02)", v); end
        else $display("R ok: ERR 0x01 after the START (RESET_FLAG kept)");
        r14_write(7'h06, 8'hFF);
        // ---------------- D
        while (dut.seq_state !== 4'd6) @(posedge MCLK);
        repeat (11 * 32768) @(posedge MCLK);            // 11 ms unread: the FIFO overflows
        r14_read(7'h07, v);
        $display("D: DFLAG 0x%02h before the APPLY (OVERRUN 1 expected)", v);
        r14_cmd(8'h33);                                 // APPLY in RUN (accepted: the FIFO is emptied)
        while (dut.seq_state !== 4'd7) @(posedge MCLK);
        repeat (2000) @(posedge MCLK);
        r14_read(7'h07, v);
        r14_read(7'h03, st);
        if (v[0] !== 1'b1 || st[STATUS_ALERT_LSB] !== 1'b1) begin
            errors++;
            $display("D FAIL: DFLAG 0x%02h, STATUS 0x%02h after an accepted APPLY: OVERRUN and ALERT expected (DFLAG is W1C only: REG-02)", v, st);
        end else $display("D ok: DFLAG 0x%02h, STATUS 0x%02h (OVERRUN and ALERT kept)", v, st);
        r14_cmd(8'h22);                                 // STOP
        while (dut.seq_state !== 4'd0) @(posedge MCLK);
        repeat (200) @(posedge MCLK);
        while (DRDY_N === 1'b0) r14_sample(st, sq, d, ok);   // the FIFO empty
        // ---------------- E
        r14_write(7'h07, 8'hFF);
        r14_write(7'h06, 8'hFF);
        r14_read(7'h06, v);
        r14_read(7'h03, st);
        $display("E: ERR 0x%02h, STATUS 0x%02h before the read (ALERT 0 expected), FIFO level %0d", v, st, dut.fifo_level);
        arm_e = 1'b1;
        r14_sample(st, sq, d, ok);
        if (n_forced != 1) begin errors++; $display("E not exercised"); end
        else if (!ok || st[SMP_VALID_LSB] !== 1'b0 || st[SMP_ERR_LSB] !== 1'b1) begin
            errors++;
            $display("E FAIL: the empty word's status 0x%02h (CRC %b): ERR %b, but ALERT was 1 in the copy's cycle (spec 3.4: ALERT at that time)",
                     st, ok, st[SMP_ERR_LSB]);
        end else $display("E ok: the empty word's status 0x%02h (ERR = ALERT of the copy's cycle)", st);
        $display("%s: tb_c35_flags (%0d errors)", errors == 0 ? "PASS" : "FAIL", errors);
        $finish;
    end
endmodule
`default_nettype wire
