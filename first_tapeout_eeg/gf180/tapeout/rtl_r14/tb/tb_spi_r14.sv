// tb_spi_r14 - random SPI frames into eeg_digital_top (r14); every frame is logged for tb/check_spi_trace.py, which
// replays it through the SPI transition table of gf180/tapeout/rtl/spec/fsm_spec.py (VER-09 for the SPI).
//
// Frames: register writes (shadows, IF_CFG, ERR, DFLAG, TEST_KEY, test registers, read-only and undefined addresses),
// commands (FLUSH, APPLY, APPLY_NR, unknown codes, rarely START, STOP, SOFT_RESET), single and burst reads of any
// address, sample reads of 0..11 bytes, with or without a partial last byte, with a wrong CRC now and then, and FLUSH
// followed at once by a sample read (the copy can stop being the head during the read), and sample reads timed so
// that a sample is stored while they run (an empty or flushed copy must not take it). The block runs (START) at
// 128 kHz and at 64 kHz (where a second command can arrive while one is pending), so `busy` and `head` take both
// values. Per frame: the bits sent and received, and what the block did (commit, errors, copy, pop), with the
// conditions that come from outside the SPI (pending command, the FIFO's held copy) at the moment they are used,
// and the flushes from the copy to the pop request (the checker derives `head` from those and the copied word).
// Usage: vvp tb_spi_r14.vvp [+n=4000] [+seed=1] [+log=build/spi_trace.txt]
`timescale 1ns / 1ps
`default_nettype none

module tb_spi_r14;
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
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));       // a busy but legal code stream

    `include "spi_bfm_r14.svh"

    // ------------------------------------------------------------------ per-frame observation
    integer n_we, n_ferr, n_cerr, n_aerr, n_snap, n_preq, n_pop, n_soft, n_fl;
    logic [6:0]  we_addr;
    logic [7:0]  we_data, we_ev, st_cs;
    logic        we_wok, we_soft, we_busy, we_sserr, we_unl, head_at_req, crc_at_cs;
    logic [47:0] snap_word;
    string       loads;
    always @(negedge CS_N) begin
        n_we = 0; n_ferr = 0; n_cerr = 0; n_aerr = 0; n_snap = 0; n_preq = 0; n_pop = 0; n_soft = 0; n_fl = 0;
        we_addr = 0; we_data = 0; we_ev = 0; we_wok = 0; we_soft = 0; we_busy = 0; we_sserr = 0; we_unl = 0;
        head_at_req = 0; snap_word = 0; loads = "";
    end
    always @(posedge MCLK) begin
        // a flush from the copy's cycle up to the pop request's cycle (both included), counted before this cycle's
        // copy and request update their counters
        if (dut.seq_flush && (n_snap > 0 || dut.smp_snap) && n_preq == 0) n_fl = n_fl + 1;
        if (dut.u_spi.cs_start) begin st_cs = dut.status_byte; crc_at_cs = dut.crc_en; end
        if (dut.reg_we) begin
            n_we = n_we + 1;
            we_addr = dut.reg_addr; we_data = dut.reg_wdata; we_wok = dut.u_regs.w_ok; we_soft = dut.u_regs.soft_reset;
            we_ev = dut.u_regs.ev_err; we_sserr = dut.seq_serr; we_busy = dut.u_regs.pend && !dut.cmd_ack;
            we_unl = dut.u_regs.unlocked;
        end
        if (dut.frame_err) n_ferr = n_ferr + 1;
        if (dut.crc_err)   n_cerr = n_cerr + 1;
        if (dut.addr_err)  n_aerr = n_aerr + 1;
        if (dut.smp_snap)  begin n_snap = n_snap + 1; snap_word = dut.smp_word; end
        if (dut.smp_pop)   begin n_preq = n_preq + 1; head_at_req = dut.u_fifo.held && !dut.seq_flush; end
        if (dut.u_fifo.pop_ok) n_pop = n_pop + 1;
        if (dut.soft_req)  n_soft = n_soft + 1;
        // every byte loaded into MISO's shift register: (state, address, byte)
        if (dut.u_spi.sclk_fall && dut.u_spi.bit_cnt == 3'd0 && !dut.u_spi.cs_start && !dut.u_spi.cs_end)
            loads = {loads, $sformatf("%0d:%02h:%02h,", dut.u_spi.st, dut.u_spi.reg_addr, dut.u_spi.tx_next)};
    end

    // ------------------------------------------------------------------ frames
    integer fd, nfr, seed;
    string  logname;
    integer nb, xb, kind;
    logic [7:0] a, d;

    function automatic logic [7:0] crc2(input logic [7:0] b0, input logic [7:0] b1);
        return tb_crc8_update(tb_crc8_update(8'h00, b0), b1);
    endfunction

    task automatic frame(input integer nbytes, input integer extra, input string tag);
        string s;
        spi_xfer(nbytes, extra);
        repeat (6) @(posedge MCLK);                    // the CS_N-rising actions (2-3 MCLK) and the pop (1 more)
        s = $sformatf("F %0d %s crc=%0d nbits=%0d tx=", nfr, tag, crc_at_cs, 8 * nbytes + extra);
        for (int i = 0; i < nbytes; i++) s = {s, $sformatf("%02h", spi_tx[i])};      // complete bytes only
        s = {s, " rx="};
        for (int i = 0; i < nbytes; i++) s = {s, $sformatf("%02h", spi_rx[i])};
        s = {s, $sformatf(" st=%02h we=%0d wa=%02h wd=%02h wok=%0d soft=%0d ev=%02h sserr=%0d busy=%0d unl=%0d",
                          st_cs, n_we, we_addr, we_data, we_wok, we_soft, we_ev, we_sserr, we_busy, we_unl)};
        s = {s, $sformatf(" ferr=%0d cerr=%0d aerr=%0d snap=%0d sw=%012h preq=%0d head=%0d fl=%0d pop=%0d nsoft=%0d loads=%s",
                          n_ferr, n_cerr, n_aerr, n_snap, snap_word, n_preq, head_at_req, n_fl, n_pop, n_soft, loads)};
        $fdisplay(fd, "%s", s);
        nfr = nfr + 1;
    endtask

    // the frame length: mostly the right one, sometimes one byte short or long, sometimes a partial byte
    task automatic shape(input integer right, output integer nbytes, output integer extra);
        integer r;
        r = $urandom_range(0, 99);
        nbytes = right;
        if (r < 8)       nbytes = (right > 0) ? right - 1 : 0;
        else if (r < 14) nbytes = right + 1;
        else if (r < 17) nbytes = $urandom_range(0, 12);
        extra = ($urandom_range(0, 99) < 12) ? $urandom_range(1, 7) : 0;
        if (nbytes + (extra > 0 ? 1 : 0) > 15) nbytes = 14;
    endtask

    logic crc_model = 1'b0;                        // what the tb believes CRC_EN is (for building good frames)
    task automatic wr(input logic [6:0] addr, input logic [7:0] val, input integer good, input string tag);
        integer n, x;
        spi_tx[0] = {1'b0, addr}; spi_tx[1] = val; spi_tx[2] = crc2(spi_tx[0], val);
        for (int i = 3; i < 16; i++) spi_tx[i] = $urandom;
        if (!good) begin
            if ($urandom_range(0, 1)) spi_tx[2] = spi_tx[2] ^ (8'h01 << $urandom_range(0, 7));   // wrong CRC
            shape(crc_model ? 3 : 2, n, x);
        end else begin
            n = crc_model ? 3 : 2; x = 0;
        end
        frame(n, x, tag);
    endtask

    // audit round 7: SCLK and MOSI are shared between chips. Another chip's frame (this CS_N high; its own CS_N low
    // 5 MCLK or more before its first SCLK edge, so its edges come after this chip's CS_N synchronizer has let go)
    // must do nothing here: no state, commit, copy, pop or flag, MISO not driven. MISO_OE is off as CS_N rises.
    logic   other_on = 1'b0;
    integer n_other = 0, n_other_bad = 0, oseed = 20261120;
    task automatic other_chip(input integer nbits);
        other_on = 1'b1;
        #(160.0);                                      // the other chip's CS_N setup (5 MCLK or more)
        for (int n = 0; n < nbits; n++) begin
            MOSI = $random(oseed);
            SCLK = 1'b1; #(spi_high); SCLK = 1'b0; #(spi_low);
        end
        MOSI = 1'b0;
        #(160.0);
        other_on = 1'b0;
        n_other = n_other + 1;
    endtask
    always @(posedge MCLK)
        if (other_on && (dut.reg_we || dut.smp_pop || dut.smp_snap || dut.frame_err || dut.crc_err || dut.addr_err ||
                         MISO_OE !== 1'b0 || dut.u_spi.st !== 4'd0)) begin
            n_other_bad = n_other_bad + 1;
            if (n_other_bad <= 5) $display("FAIL: tb_spi_r14 @%0t: activity during another chip's frame (st %0d)", $time, dut.u_spi.st);
        end
    always @(posedge CS_N) begin
        #1;
        if (MISO_OE !== 1'b0) $display("FAIL: tb_spi_r14 @%0t: MISO_OE still on after CS_N rose", $time);
    end

    integer i_run;
    // watchdog (audit round 5): a frame takes about 0.34 ms of simulated time; 1 ms per frame ends a run that waits for
    // an event the RTL never gives (cic_stb, tick) as a failure instead of a hang
    initial begin
        #1;
        #(i_run * 1.0e6);
        $display("FAIL: tb_spi_r14 watchdog: not finished after %0d ms of simulated time", i_run);
        $finish;
    end
    initial begin
        if (!$value$plusargs("n=%d", i_run)) i_run = 4000;
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        if (!$value$plusargs("log=%s", logname)) logname = "build/spi_trace.txt";
        void'($urandom(seed));
        fd = $fopen(logname, "w");
        nfr = 0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        // run: T_WARM 5 ms, T_REC 29 (minimum), START; random frames keep arriving meanwhile
        wr(7'h52, 8'd29, 1, "setup");
        wr(7'h10, 8'h11, 1, "setup");
        for (int k = 0; k < i_run; k++) begin
            // halfway: 64 kHz (STOP, CHOP_FAST 0, APPLY, START)
            if (k == i_run / 2) begin
                wr(7'h10, 8'h22, 1, "setup"); repeat (2000) @(posedge MCLK);
                wr(7'h26, 8'h00, 1, "setup"); wr(7'h10, 8'h33, 1, "setup"); repeat (2000) @(posedge MCLK);
                wr(7'h10, 8'h11, 1, "setup");
            end
            // every 400 frames a SOFT_RESET (every other one right after a FLUSH: with a command pending at 64 kHz),
            // then running again; the random commands below reach STOP and SOFT_RESET only now and then
            if (k % 400 == 200) begin
                spi_tidle = 125.0;
                if (k % 800 == 200) wr(7'h10, 8'h55, 1, "cmd");
                wr(7'h10, 8'hA5, 1, "cmd");
                crc_model = dut.crc_en;
                repeat (300) @(posedge MCLK);
                if (dut.a_chop_fast !== (k < i_run / 2)) begin
                    wr(7'h26, {7'd0, k < i_run / 2}, 1, "setup"); wr(7'h10, 8'h33, 1, "setup");
                    repeat (2000) @(posedge MCLK);
                end
                wr(7'h52, 8'd29, 1, "setup");
                wr(7'h10, 8'h11, 1, "setup");
            end
            spi_tidle = ($urandom_range(0, 3) == 0) ? 125.0 : 600.0 + $urandom_range(0, 20000);
            if ($unsigned($random(oseed)) % 100 < 15)  // another chip's frame (its own random stream: the frames
                other_chip(1 + $unsigned($random(oseed)) % 40);   // of this chip are the same as before)
            kind = $urandom_range(0, 99);
            if (kind < 22) begin                                   // write a register (random address class)
                case ($urandom_range(0, 9))
                    0, 1, 2: a = 7'h23 + $urandom_range(0, 5);      // shadows (not M, range: START stays legal)
                    3:       a = 7'h55;                             // IF_CFG (CRC_EN, DRDY_MODE)
                    4:       a = 7'h06 + $urandom_range(0, 1);      // ERR, DFLAG (W1C)
                    5:       a = 7'h11;                             // TEST_KEY
                    6:       a = 7'h60 + $urandom_range(0, 2);      // test registers
                    7:       a = $urandom_range(0, 5);              // read-only
                    8:       a = 7'h30 + $urandom_range(0, 8);      // active copies (read-only)
                    default: a = $urandom_range(0, 127);            // anything
                endcase
                if (a == 7'h10 || (a >= 7'h50 && a <= 7'h54) || (a >= 7'h20 && a <= 7'h22) || a == 7'h26)
                    a = 7'h24;                                      // commands, timers, M, range, rate: separate
                case (a)
                    7'h11:   d = ($urandom_range(0, 2) == 0) ? 8'h3C : (($urandom_range(0, 1)) ? 8'h00 : $urandom);
                    7'h55:   d = $urandom_range(0, 3);
                    default: d = $urandom;
                endcase
                wr(a, d, $urandom_range(0, 99) < 70, "wr");
                if (a == 7'h55 && dut.crc_en !== crc_model) crc_model = dut.crc_en;
            end else if (kind < 30) begin                          // a command (seldom one that stops the data)
                case ($urandom_range(0, 39))
                    0, 1, 2, 3, 4, 5, 6, 7, 8, 9: d = 8'h55;        // FLUSH
                    10, 11, 12, 13, 14, 15:       d = 8'h44;        // APPLY_NR (CFG_ERR unless nr_ok)
                    16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27: d = $urandom;   // mostly unknown
                    28, 29, 30, 31:               d = 8'h11;        // START (STATE_ERR while running)
                    32:                           d = 8'h33;        // APPLY
                    33:                           d = 8'h22;        // STOP
                    34:                           d = 8'hA5;        // SOFT_RESET
                    default:                      d = 8'h3C;        // the key's value as a command (unknown)
                endcase
                wr(7'h10, d, $urandom_range(0, 99) < 85, "cmd");
                if (dut.crc_en !== crc_model) crc_model = dut.crc_en;     // after SOFT_RESET
                if (d == 8'h22 || d == 8'hA5) begin                     // keep it running
                    repeat (300) @(posedge MCLK);
                    if (dut.a_chop_fast !== (k < i_run / 2)) begin
                        wr(7'h26, {7'd0, k < i_run / 2}, 1, "setup"); wr(7'h10, 8'h33, 1, "setup");
                        repeat (2000) @(posedge MCLK);
                    end
                    wr(7'h52, 8'd29, 1, "setup");
                    wr(7'h10, 8'h11, 1, "setup");
                end
            end else if (kind < 34) begin                          // two commands back to back (busy at 64 kHz)
                spi_tidle = 125.0;
                wr(7'h10, 8'h55, 1, "cmd");
                case ($urandom_range(0, 3))
                    0:       d = 8'h55;
                    1:       d = 8'h44;
                    2:       d = $urandom;
                    default: d = 8'h11;
                endcase
                wr(7'h10, d, 1, "cmd2");
            end else if (kind < 37) begin                          // an empty frame or part of a header
                spi_tx[0] = $urandom;
                frame(0, $urandom_range(0, 7), "part");
            end else if (kind < 42) begin                          // a sample read across the next store
                real t_out;
                @(posedge dut.cic_stb);
                t_out = $realtime + 1.0e6;                         // the next output time (1024 frames)
                @(posedge dut.tick);
                while (t_out - $realtime > 25000.0) @(posedge dut.tick);   // a tick at most 25 us before it
                spi_tidle = 125.0;
                if ($urandom_range(0, 1)) wr(7'h10, 8'h55, 1, "cmd");      // half of them after a FLUSH
                spi_tx[0] = SMP_HDR;
                for (int i = 1; i < 16; i++) spi_tx[i] = 8'h00;
                frame(8, 0, "smpt");
            end else if (kind < 56) begin                          // read registers
                integer n, x;
                spi_tx[0] = {1'b1, 7'($urandom_range(0, 127))};
                if (spi_tx[0][6:0] == 7'h40) spi_tx[0] = 8'h80 | 8'h06;
                for (int i = 1; i < 16; i++) spi_tx[i] = 8'h00;
                if (crc_model) shape(3, n, x);
                else begin n = 1 + $urandom_range(1, 6); x = ($urandom_range(0, 99) < 10) ? $urandom_range(1, 7) : 0; end
                frame(n, x, "rd");
            end else if (kind < 90) begin                          // a sample read
                integer n, x;
                if ($urandom_range(0, 3) != 0) begin                // mostly wait for a sample (at most 1.2 ms)
                    real t0;
                    t0 = $realtime;
                    while (DRDY_N !== 1'b0 && ($realtime - t0) < 1.2e6) @(posedge MCLK);
                end
                spi_tx[0] = SMP_HDR;
                for (int i = 1; i < 16; i++) spi_tx[i] = 8'h00;
                shape(8, n, x);
                frame(n, x, "smp");
            end else begin                                         // FLUSH, then a sample read at once
                integer n, x;
                spi_tidle = 125.0;
                wr(7'h10, 8'h55, 1, "cmd");
                spi_tx[0] = SMP_HDR;
                for (int i = 1; i < 16; i++) spi_tx[i] = 8'h00;
                shape(8, n, x);
                frame(n, x, "smp");
            end
        end
        $fclose(fd);
        $display("tb_spi_r14: %0d frames, %0d SPI timing errors, %0d frames of another chip on SCLK -> %s", nfr, spi_errors,
                 n_other, logname);
        $finish;
    end
endmodule

`default_nettype wire
