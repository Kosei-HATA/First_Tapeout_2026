// tb_a31_crcoff - audit round 31 (A, aside). CRC-off operation (5.4 step 4, last item, round 30 B2): one header bit of
// a write lands on a writable neighbour outside the read-back set 0x20..0x28 / 0x50..0x54: ALERT_MASK_D 0x09 -> ALERT_MASK
// 0x08 (step 3 writes ALERT_MASK_D = 0x00), T_ELEC 0x51 -> IF_CFG 0x55 and T_RST 0x54 -> IF_CFG 0x55.
`timescale 1ns / 1ps
`default_nettype none
module tb_a31_crcoff;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd14 + 5'($urandom % 4);
    logic [7:0] v, v2, want [0:127];
    integer a, bad, npulse = 0, lowlen = 0;
    real tf;
    always @(negedge DRDY_N) tf = $realtime;
    always @(posedge DRDY_N) if ($realtime - tf < 10000.0) npulse = npulse + 1;
    task automatic readback(input string tag);
        bad = 0;
        for (a = 8'h20; a <= 8'h28; a++) begin r14_read(7'(a), v); r14_read(7'(a), v2); if (v !== want[a] || v2 !== want[a]) bad++; end
        for (a = 8'h50; a <= 8'h54; a++) begin r14_read(7'(a), v); r14_read(7'(a), v2); if (v !== want[a] || v2 !== want[a]) bad++; end
        $display("%s: CRC-off read-back of 0x20..0x28 and 0x50..0x54 twice: %0d mismatches", tag, bad);
    endtask
    initial begin
        for (a = 0; a < 128; a++) want[a] = 8'h00;
        want[8'h23] = 8'h03; want[8'h24] = 8'h08; want[8'h25] = 8'h01; want[8'h26] = 8'h01; want[8'h27] = 8'h13;
        want[8'h28] = 8'h07; want[8'h50] = 8'h05; want[8'h51] = 8'h00; want[8'h52] = 8'h20; want[8'h53] = 8'h03;
        want[8'h54] = 8'h0D;
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_read(7'h06, v); r14_write(7'h06, v);
        // step 3 (CRC off): ALERT_MASK_D = 0x00, T_ELEC = 2, M 40 range 1; two headers lose bit 0 / bit 2
        r14_write(7'h08, 8'h00);                     // sent as [0x09, 0x00], arrives as [0x08, 0x00]
        $display("ALERT_MASK_D write landed on ALERT_MASK: MISO %02h %02h (rule (a) holds), ERR 0x%02h", spi_rx[0], spi_rx[1], dut.u_regs.err);
        r14_write(7'h55, 8'h02);                     // sent as [0x51, 0x02] (T_ELEC 2), arrives as [0x55, 0x02]
        $display("T_ELEC write landed on IF_CFG: MISO %02h %02h, ERR 0x%02h", spi_rx[0], spi_rx[1], dut.u_regs.err);
        r14_write(7'h20, 8'h00); r14_write(7'h21, 8'd40); r14_write(7'h22, 8'h01);
        want[8'h21] = 8'd40; want[8'h22] = 8'h01; want[8'h51] = 8'h02;
        r14_read(7'h06, v); $display("ERR after the writes 0x%02h (no bit: nothing to rewrite)", v);
        // step 3's read-back of the registers written (ALERT_MASK_D, T_ELEC, OFF_*): the lost ones are rewritten
        r14_read(7'h09, v); r14_read(7'h09, v2); $display("ALERT_MASK_D read back 0x%02h 0x%02h -> rewritten", v, v2);
        r14_write(7'h09, 8'h00);
        r14_read(7'h51, v); r14_read(7'h51, v2); $display("T_ELEC read back 0x%02h 0x%02h -> rewritten", v, v2);
        r14_write(7'h51, 8'h02);
        readback("before START (step 4, CRC off)");
        r14_read(7'h08, v); r14_read(7'h55, v2);
        $display("not read back: ALERT_MASK 0x%02h (host: 0xFF), IF_CFG 0x%02h (host: 0x00, level mode)", v, v2);
        r14_cmd(CMD_START);
        while (dut.seq_state !== ST_RUN) @(posedge MCLK);
        #(5.0e6);
        $display("RUN 5 ms: DRDY_N pulses of < 10 us: %0d (level mode expected: low while the FIFO holds samples)", npulse);
        // a refused command: two-step APPLY_NR -> CFG_ERR; ALERT in the next header?
        r14_write(7'h21, 8'd42); r14_cmd(CMD_APPLY_NR); #(40000.0);
        r14_read(7'h03, v);
        $display("after a refused APPLY_NR: ERR 0x%02h, STATUS header 0x%02h (ALERT bit %0d)", dut.u_regs.err, spi_rx[0], spi_rx[0][5]);
        // T_ELEC = 60 ms (0x3C) sent as [0x51, 0x3C] arrives as [0x11, 0x3C] (bit 6): the key
        r14_write(7'h11, 8'h3C);
        $display("T_ELEC 60 landed on TEST_KEY: ERR 0x%02h, unlocked %0d (TEST_KEY reads 0x00: not visible)", dut.u_regs.err, dut.u_regs.unlocked);
        r14_write(7'h51, 8'h3C);                     // step 3 rewrites the lost T_ELEC
        // a later OFF_M_L write [0x21, 0x02] arriving as [0x61, 0x02] (bit 6): TEST_CTRL = CHOP_STOP
        r14_write(7'h61, 8'h02);
        $display("OFF_M_L landed on TEST_CTRL: ERR 0x%02h, TEST_CTRL shadow 0x%02h", dut.u_regs.err, {6'd0, dut.u_regs.s_cstop, dut.u_regs.s_azero});
        r14_write(7'h21, 8'h02); want[8'h21] = 8'h02; want[8'h51] = 8'h3C;
        readback("before APPLY (step 4, CRC off)");
        r14_cmd(CMD_APPLY); #(40000.0);
        $display("after the APPLY: ERR 0x%02h, CHOP_EN %b", dut.u_regs.err, CHOP_EN);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
