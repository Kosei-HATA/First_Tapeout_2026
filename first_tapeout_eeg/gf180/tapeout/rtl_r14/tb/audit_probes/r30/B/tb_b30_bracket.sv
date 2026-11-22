// tb_b30_bracket - audit round 30 (B): step 3's test-register bracket (round 29) replayed literally with one fault.
// Case 1 (CRC on): the bracket sets TEST_MUX = 0x1C, TEST_CTRL = 0x02; the TEST_CTRL write of (2) gets one MOSI bit
// error in its CRC byte (CRC_ERR). (3) reads back, (4) locks, (5) writes TEST_CTRL 0x00 and expects exactly ADDR_ERR.
// The bracket writes ERR back only on success; on "another bit" it redoes the whole bracket, whose (1) requires ERR
// to have no bit: replayed three times (rule (d)).
// Case 2 (CRC off, the operation step 4 allows): the lock write [0x11, 0x00] with header bit 6 flipped ([0x51, 0x00]):
// T_ELEC is written 0, the key stays open, MISO passes rule (a); (5)'s TEST_CTRL 0x00 is accepted and clears the
// test value the bracket set and (3) confirmed; the host then only locks again.
`timescale 1ns / 1ps
`default_nettype none
module tb_b30_bracket;
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
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"
    logic [7:0] e, v1, v2;
    function automatic logic [7:0] crc2(input logic [7:0] b0, input logic [7:0] b1);
        return tb_crc8_update(tb_crc8_update(8'h00, b0), b1);
    endfunction
    task automatic rd2(input logic [6:0] a, output logic [7:0] v);
        logic [7:0] x, y;
        r14_read(a, x); r14_read(a, y);
        v = x;
        if (x !== y) $display("  read 0x%02h: %02h then %02h (no agreement)", a, x, y);
    endtask
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);                                     // step 2: RESET_FLAG cleared
        // ------------------------------------------------------------ case 1: CRC on
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h51, 8'h00);
        r14_read(7'h06, e); $display("case 1: ERR before the bracket 0x%02h", e);
        for (int pass = 1; pass <= 3; pass++) begin
            r14_write(7'h11, 8'h3C);                                 // (1) unlock ...
            r14_read(7'h06, e);                                      //     ... and ERR must have no bit
            $display("case 1, bracket pass %0d: (1) ERR 0x%02h -> %s", pass, e,
                     (e == 8'h00) ? "no bit, go on" : "a bit: redo the whole bracket (nothing writes ERR back)");
            if (e != 8'h00) continue;
            r14_write(7'h60, 8'h1C);                                 // (2)
            spi_tx[0] = 8'h61; spi_tx[1] = 8'h02; spi_tx[2] = crc2(8'h61, 8'h02) ^ 8'h10;  // one MOSI bit error
            spi_xfer(3, 0);
            r14_write(7'h62, 8'h00);
            rd2(7'h60, v1); rd2(7'h61, v2);                          // (3)
            $display("case 1: (3) TEST_MUX 0x%02h, TEST_CTRL 0x%02h (written 0x1C, 0x02)", v1, v2);
            r14_write(7'h11, 8'h00);                                 // (4)
            r14_write(7'h61, 8'h00);                                 // (5)
            r14_read(7'h06, e);
            $display("case 1: (5) ERR 0x%02h (%s)", e, (e == 8'h08) ? "exactly ADDR_ERR" : "another bit: redo the bracket");
            if (e == 8'h08) begin r14_write(7'h06, e); break; end
        end
        r14_read(7'h06, e); $display("case 1: after 3 passes ERR 0x%02h, key %s, TEST_CTRL shadow 0x%02h",
                                     e, dut.u_regs.unlocked ? "open" : "locked", {6'd0, dut.u_regs.s_cstop, dut.u_regs.s_azero});
        // ------------------------------------------------------------ case 2: CRC off
        RESET_N = 1'b0; bfm_crc_en = 1'b0; repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
        r14_write(7'h51, 8'h05);                                     // T_ELEC 5 ms (the electrode's wait)
        r14_write(7'h11, 8'h3C);                                     // (1)
        r14_write(7'h60, 8'h1C); r14_write(7'h61, 8'h02); r14_write(7'h62, 8'h00);   // (2)
        rd2(7'h60, v1); rd2(7'h61, v2);
        $display("case 2: (3) TEST_MUX 0x%02h, TEST_CTRL 0x%02h", v1, v2);
        spi_tx[0] = 8'h11 ^ 8'h40; spi_tx[1] = 8'h00; spi_xfer(2, 0);   // (4) lock, header bit 6 flipped -> 0x51
        $display("case 2: (4) lock frame MISO %02h %02h (rule (a): fixed bits and 0x00)", spi_rx[0], spi_rx[1]);
        r14_read(7'h06, e); $display("case 2: ERR after the lock 0x%02h", e);
        r14_write(7'h61, 8'h00);                                     // (5)
        r14_read(7'h06, e);
        $display("case 2: (5) ERR 0x%02h -> %s", e, (e == 8'h08) ? "lock confirmed" : "accepted: lock again");
        r14_write(7'h11, 8'h00); r14_write(7'h61, 8'h00); r14_read(7'h06, e);
        $display("case 2: (4)(5) again: ERR 0x%02h; key %s; TEST_CTRL shadow 0x%02h (the host's (3) saw 0x02); T_ELEC 0x%02h (written 0x05)",
                 e, dut.u_regs.unlocked ? "open" : "locked", {6'd0, dut.u_regs.s_cstop, dut.u_regs.s_azero}, dut.u_regs.r_te);

        // ------------------------------------------------------------ case 3: CRC on, round 29's own case: the lock
        // write loses one SCLK pulse at the chip (the host sends 24 bits, the chip counts 23: FRAME_ERR, MISO passes rule
        // (a)); the bracket restores the reset values (the use after a test)
        RESET_N = 1'b0; bfm_crc_en = 1'b0; repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h51, 8'h00);
        for (int pass = 1; pass <= 3; pass++) begin
            r14_write(7'h11, 8'h3C);                                 // (1)
            r14_read(7'h06, e);
            $display("case 3, bracket pass %0d: (1) ERR 0x%02h -> %s", pass, e,
                     (e == 8'h00) ? "no bit, go on" : "a bit: redo the whole bracket (nothing writes ERR back)");
            if (e != 8'h00) continue;
            r14_write(7'h60, 8'h00); r14_write(7'h61, 8'h00); r14_write(7'h62, 8'h00);   // (2)
            rd2(7'h60, v1); rd2(7'h61, v2);                          // (3)
            spi_tx[0] = 8'h11; spi_tx[1] = 8'h00; spi_tx[2] = crc2(8'h11, 8'h00);
            spi_xfer(2, 7);                                          // (4): the chip counts 23 of the host's 24 pulses
            $display("case 3: (4) lock frame MISO %02h %02h (rule (a) passes)", spi_rx[0], spi_rx[1]);
            r14_write(7'h61, 8'h00);                                 // (5)
            r14_read(7'h06, e);
            $display("case 3: (5) ERR 0x%02h (%s)", e, (e == 8'h08) ? "exactly ADDR_ERR" : "another bit: redo the bracket");
            if (e == 8'h08) begin r14_write(7'h06, e); break; end
        end
        r14_read(7'h06, e); $display("case 3: after 3 passes ERR 0x%02h, key %s (rule (d): RESET_N of every chip)",
                                     e, dut.u_regs.unlocked ? "open" : "locked");

        // ------------------------------------------------------------ case 4: CRC on, no fault in the bracket's frames:
        // one sample read during the bracket fails the host's CRC (one MISO bit), and step 6 re-reads it with 8 more
        // SCLK (the chip flags FRAME_ERR); rule (e) keeps step 6 from writing FRAME_ERR back inside step 3's section
        RESET_N = 1'b0; bfm_crc_en = 1'b0; repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h51, 8'h00);
        for (int pass = 1; pass <= 3; pass++) begin
            r14_write(7'h11, 8'h3C);                                 // (1)
            r14_read(7'h06, e);
            $display("case 4, bracket pass %0d: (1) ERR 0x%02h -> %s", pass, e,
                     (e == 8'h00) ? "no bit, go on" : "a bit: redo the whole bracket (nothing writes ERR back)");
            if (e != 8'h00) continue;
            r14_write(7'h60, 8'h00); r14_write(7'h61, 8'h00); r14_write(7'h62, 8'h00);   // (2)
            rd2(7'h60, v1); rd2(7'h61, v2);                          // (3)
            spi_tx[0] = SMP_HDR; for (int i = 1; i < 9; i++) spi_tx[i] = 8'h00;
            spi_xfer(SMP_FRAME_LEN + 1, 0);                          // step 6: CRC failed at the host -> 8 more SCLK
            r14_write(7'h11, 8'h00);                                 // (4)
            r14_write(7'h61, 8'h00);                                 // (5)
            r14_read(7'h06, e);
            $display("case 4: (5) ERR 0x%02h (%s)", e, (e == 8'h08) ? "exactly ADDR_ERR" : "another bit: redo the bracket");
            if (e == 8'h08) begin r14_write(7'h06, e); break; end
        end

        // ------------------------------------------------------------ case 5: CRC off, the lock check (5) itself with
        // header bit 6 flipped: [0x61, 0x00] -> [0x21, 0x00] (OFF_M_L), the key already locked
        RESET_N = 1'b0; bfm_crc_en = 1'b0; repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
        r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd40);            // range 1, M 40 (the offset found)
        r14_write(7'h11, 8'h3C); r14_write(7'h60, 8'h00); r14_write(7'h61, 8'h00); r14_write(7'h11, 8'h00);
        spi_tx[0] = 8'h61 ^ 8'h40; spi_tx[1] = 8'h00; spi_xfer(2, 0);   // (5) with one header bit error
        $display("case 5: (5) frame MISO %02h %02h (rule (a) passes)", spi_rx[0], spi_rx[1]);
        r14_read(7'h06, e);
        $display("case 5: (5) ERR 0x%02h -> %s; OFF_M_L shadow %0d (was 40)", e,
                 (e == 8'h08) ? "lock confirmed" : "no ADDR_ERR: lock again", dut.u_regs.s_m[7:0]);

        // ------------------------------------------------------------ case 6: CRC off (step 4, last bullet): the
        // procedure's own W1C write-backs with header bit 5 flipped land on analog shadows, no flag, MISO passes (a)
        RESET_N = 1'b0; bfm_crc_en = 1'b0; repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
        spi_tx[0] = 8'h06 ^ 8'h20; spi_tx[1] = 8'h02; spi_xfer(2, 0);    // step 6: FRAME_ERR write-back 0x02 -> 0x26
        $display("case 6: ERR write-back [06,02] as [26,02]: MISO %02h %02h", spi_rx[0], spi_rx[1]);
        spi_tx[0] = 8'h07 ^ 8'h20; spi_tx[1] = 8'h02; spi_xfer(2, 0);    // step 8: DFLAG.OVL write-back 0x02 -> 0x27
        $display("case 6: DFLAG write-back [07,02] as [27,02]: MISO %02h %02h", spi_rx[0], spi_rx[1]);
        r14_read(7'h06, e);
        $display("case 6: ERR 0x%02h; shadows CHOP_FAST %0d (default 1), DWA_EN %0d (default 1), CHOP1_RATE %0d (default 3)",
                 e, dut.u_regs.s_fast, dut.u_regs.s_dwa, dut.u_regs.s_c1);
        r14_write(7'h22, 8'h01); r14_cmd(8'h33); repeat (2000) @(posedge MCLK);   // the next APPLY (IDLE: no pulse)
        $display("case 6: after an APPLY: CHOP_FAST active %0d, DWA_EN pin %b, CHOP1_RATE active %0d", dut.a_chop_fast, DWA_EN, dut.a_c1);
        $display("SPI errors in the bench's own checks: %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
