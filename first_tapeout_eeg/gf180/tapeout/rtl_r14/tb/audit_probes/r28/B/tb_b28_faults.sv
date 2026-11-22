// tb_b28_faults - audit round 28 (B): every single fault on every CRC frame the host procedure sends.
//  P3: each bit of each 3-byte CRC write flipped on MOSI; P8: each of the 24 pulses missed or doubled (a runt the chip
//  counts) in each CRC write; P4: each header bit of each 3-byte CRC read flipped. Checks: no register other than ERR
//  (and the FIFO's copy mark) changes unless the frame is the intended write, and the host's checks (rule (a),
//  the read CRC over the header it sent) do not accept a wrong frame silently.
`timescale 1ns / 1ps
`default_nettype none
module tb_b28_faults;
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

    // the control state the host writes (everything but ERR, DFLAG and the FIFO)
    function automatic logic [255:0] snap_regs();
        snap_regs = {dut.u_regs.s_m, dut.u_regs.s_sign, dut.u_regs.s_range, dut.u_regs.s_ibias, dut.u_regs.s_cpf,
                     dut.u_regs.s_bp, dut.u_regs.s_bn, dut.u_regs.s_fast, dut.u_regs.s_dwa, dut.u_regs.s_c1,
                     dut.u_regs.s_blank, dut.u_regs.s_atpen, dut.u_regs.s_atpsel, dut.u_regs.s_cstop, dut.u_regs.s_azero,
                     dut.u_regs.r_mask, dut.u_regs.r_mask_d, dut.u_regs.r_tw, dut.u_regs.r_te, dut.u_regs.r_trec,
                     dut.u_regs.r_tpre, dut.u_regs.r_trst, dut.u_regs.r_raw, dut.u_regs.r_dbg, dut.u_regs.r_crc,
                     dut.u_regs.r_drdy, dut.u_regs.unlocked, dut.u_regs.pend, dut.u_regs.pcode, dut.u_regs.a_m,
                     dut.seq_state, dut.u_regs.dflag};
    endfunction

    // a frame of nb bytes; flip: MOSI bit index to invert (-1 none); miss: host pulse the chip never sees (-1 none);
    // dup: host pulse before which the chip sees one extra (runt) pulse (-1 none). The host samples MISO at its rises.
    task automatic xfer(input logic [63:0] tx, input integer nb, input integer flip, input integer miss,
                        input integer dup, output logic [63:0] rx);
        integer nbits;
        nbits = 8 * nb;
        rx = '0;
        CS_N = 1'b0;
        MOSI = tx[63] ^ (flip == 0);
        #(spi_tcss);
        for (int n = 0; n < nbits; n++) begin
            if (n == dup) begin                        // a runt the chip counts (MOSI already at bit n)
                SCLK = 1'b1; #(4.0 * TMCLK); SCLK = 1'b0; #(5.0 * TMCLK);
            end
            if (n != miss) SCLK = 1'b1;
            rx[63 - n] = miso_pad;
            #(spi_high);
            SCLK = 1'b0;
            MOSI = (n + 1 < nbits) ? (tx[62 - n] ^ (flip == n + 1)) : 1'b0;
            if (n + 1 < nbits) #(spi_low);
        end
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
    endtask

    function automatic logic [7:0] c2(input logic [7:0] a, input logic [7:0] b);
        return tb_crc8_update(tb_crc8_update(8'h00, a), b);
    endfunction

    // the writes the host procedure sends (CRC on): settings, timers, masks, IF_CFG, W1C write-backs, the key, FLUSH
    logic [6:0] wa [0:20] = '{7'h20, 7'h21, 7'h22, 7'h23, 7'h24, 7'h25, 7'h26, 7'h27, 7'h28, 7'h50, 7'h51, 7'h52,
                               7'h53, 7'h54, 7'h55, 7'h08, 7'h09, 7'h06, 7'h07, 7'h11, 7'h10};
    logic [7:0] wv [0:20] = '{8'h01, 8'hDB, 8'h12, 8'h02, 8'h05, 8'h12, 8'h00, 8'h14, 8'h09, 8'h0A, 8'h05, 8'h25,
                               8'h04, 8'h0E, 8'h01, 8'h7F, 8'h00, 8'h02, 8'h02, 8'h3C, 8'h55};
    // the reads the host procedure decides from or reads back (CRC on)
    logic [6:0] ra [0:33] = '{7'h00, 7'h03, 7'h04, 7'h05, 7'h06, 7'h07, 7'h08, 7'h09, 7'h20, 7'h21, 7'h22, 7'h23,
                               7'h24, 7'h25, 7'h26, 7'h27, 7'h28, 7'h30, 7'h31, 7'h32, 7'h33, 7'h34, 7'h35, 7'h36,
                               7'h37, 7'h38, 7'h50, 7'h51, 7'h52, 7'h53, 7'h54, 7'h55, 7'h60, 7'h70};
    logic [255:0] s0, s1;
    logic [63:0] rx, tx;
    logic [7:0] e, h, v, ce;
    integer silent, aok, kinds, quiet, acc, n3, n8, n4;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h11, 8'h3C);                              // unlocked, so that TEST_MUX writes are legal
        r14_cmd(8'h11);                                       // START: samples in the FIFO for the window reads
        do begin #(200000.0); r14_read(7'h04, v); end while (v !== 8'd6);
        #(3000000.0);
        r14_read(7'h06, e); r14_write(7'h06, e);
        silent = 0; quiet = 0; acc = 0; n3 = 0; n8 = 0; n4 = 0;
        // ---------------------------------------------------------------- P3 and P8: writes
        for (int w = 0; w < 21; w++) begin
            for (int mode = 0; mode < 3; mode++) begin
                for (int k = 0; k < 24; k++) begin
                    if (wa[w] == 7'h10 && mode == 0 && k >= 8) ;   // FLUSH: every bit too (harmless)
                    tx = {1'b0, wa[w], wv[w], c2({1'b0, wa[w]}, wv[w]), 40'h0};
                    s0 = snap_regs();
                    xfer(tx, 3, mode == 0 ? k : -1, mode == 1 ? k : -1, mode == 2 ? k : -1, rx);
                    repeat (8) @(negedge MCLK);
                    s1 = snap_regs();
                    r14_read(7'h06, e);
                    aok = (rx[63:62] == 2'b10) && (rx[55:40] == 16'h0000);    // rule (a) for a write
                    // a changed control state other than ERR / DFLAG / pending command bookkeeping
                    if (mode == 0) n3 = n3 + 1; else n8 = n8 + 1;
                    if (s1[255:3] !== s0[255:3] && !(wa[w] == 7'h10)) begin
                        silent = silent + 1;
                        $display("CHANGE: write %02h<=%02h, %s %0d: rule(a) %0d ERR %02h", wa[w], wv[w],
                                 mode == 0 ? "flip" : mode == 1 ? "miss" : "dup", k, aok, e);
                    end
                    if (aok && e == 8'h00 && !(wa[w] == 7'h06 || wa[w] == 7'h07)) begin
                        quiet = quiet + 1;
                        $display("QUIET: write %02h<=%02h, %s %0d: rule (a) passes, ERR 0x00 (state %s)", wa[w], wv[w],
                                 mode == 0 ? "flip" : mode == 1 ? "miss" : "dup", k, s1[255:3] === s0[255:3] ? "unchanged" : "CHANGED");
                    end
                    if (e != 8'h00) r14_write(7'h06, e);
                    // put the intended value back (the host's next write), then clear
                    if (wa[w] != 7'h10 && wa[w] != 7'h06 && wa[w] != 7'h07) r14_write(wa[w], wv[w]);
                    r14_read(7'h06, e); if (e != 8'h00) r14_write(7'h06, e);
                    if (wa[w] == 7'h10) begin #(40000.0); end
                end
            end
        end
        $display("P3/P8: %0d flipped and %0d slipped CRC writes; %0d changed the control state; %0d passed rule (a) with ERR 0x00",
                 n3, n8, silent, quiet);
        // ---------------------------------------------------------------- P4: reads
        for (int r = 0; r < 34; r++) begin
            for (int b = 0; b < 8; b++) begin
                h = {1'b1, ra[r]};
                tx = {h, 16'h0000, 40'h0};
                s0 = snap_regs();
                xfer(tx, 3, b, -1, -1, rx);
                repeat (8) @(negedge MCLK);
                s1 = snap_regs();
                n4 = n4 + 1;
                if (rx[63:62] == 2'b10 && rx[47:40] == c2(h, rx[55:48])) begin
                    acc = acc + 1;
                    $display("ACCEPT: read %02h with header bit %0d flipped (chip got %02h): host reads %02h, CRC valid",
                             h, 7 - b, h ^ (8'h80 >> b), rx[55:48]);
                end
                if (s1[255:3] !== s0[255:3]) $display("CHANGE: read %02h bit %0d", h, 7 - b);
                r14_read(7'h06, e); if (e != 8'h00) r14_write(7'h06, e);
            end
        end
        $display("P4: %0d corrupted CRC reads, %0d accepted by the host's checks", n4, acc);
        $finish;
    end
endmodule
`default_nettype wire
