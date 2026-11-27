// tb_e2e_r15 - VER-04 (11/28): the r15 block (eeg_digital_top of rtl_r15) with a whole code stream of the CT loop model
// (rtl/model/ct2_codes.py; rtl/build/e2e/<case>.codes, one byte per frame: s4 4.26 s, s20 20.26 s), run like the host:
//   * reset; ID, VERSION, CAPS; CRC on (IF_CFG.CRC_EN, every later register access with its CRC); START with the
//     default timers and trims; STATE polled over SPI until RUN;
//   * every sample read over SPI as the host's step 6 does: the first half in the default level mode of DRDY_N (read
//     while it is Low), the second half in the pulse mode (IF_CFG.DRDY_MODE 1, one read per pulse); the sample's CRC
//     checked, the status byte VALID alone (no OVERRUN, OVL, CHANGED, ERR: the streams' codes are 3..27), SEQ +1
//     from read to read;
//   * backlogs: now and then the reads wait 1..6 outputs and then read the queue in a row (the FIFO's order);
//   * LATEST read every 64 samples: the last stored output (status, SEQ, DATA), CRC from LAT_HDR, nothing popped;
//   * at the end STOP; DFLAG, ERR and DROP_CNT 0, CFG_GEN 1, STATE IDLE; no FIFO drop in the whole run.
// The stream: CODE changes at frame cycle 1 (e2, as eeg_adc_dig's CODE) to the stream's next byte; the frame count
// since the RESET_N release is the position in the stream (+start=<offset> for a chunk; the stream wraps at its end).
// Every CIC input is checked to be its frame's code, input i = stream position start + i. The log (+log=<file>):
// 'C s n_in' for the armed clear at the output with SEQ s (ALIGN; n_in = the inputs taken so far), 'S seq data status'
// for every sample read, 'E ...' the end. tb/check_e2e_r15.py runs the golden CIC (rtl/model/cic_golden.py) on the
// stream from the clear and compares every sample bit for bit.
// RESET_N and every SPI frame change at an MCLK falling edge or between edges (the lockstep gate level,
// gl_r15/gl_shadow_r15.sv compiled as a second root with +define+TB=tb_e2e_r15, takes them like the RTL).
// The ADC block (gl_r15/sys_adc_r15.sv as a further root, +define+TB=tb_e2e_r15 and tb/sys_e2e_r15.svh) can drive
// CODE from TH: `nxt` is the code of the coming e2.
// Plusargs: +codes=<file> [+nsamp=<n>] [+log=<file>] [+start=<frame>]
`timescale 1ns / 1ps
`default_nettype none

module tb_e2e_r15;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    localparam int  FD = 8;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG;
    wire [3:0] CPF_TRIM, OFEN;
    wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(FD)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    `include "spi_bfm_r14.svh"

    integer errors = 0, checks = 0;
    task automatic fail(input string msg);
        errors = errors + 1;
        if (errors <= 30) $display("FAIL @%0t: %s", $time, msg);
    endtask
    task automatic expect8(input logic [7:0] got, input logic [7:0] want, input string what);
        checks = checks + 1;
        if (got !== want) fail($sformatf("%s: 0x%02h, expected 0x%02h", what, got, want));
    endtask

    // ---------------- the code stream
    string  codes_file, log_file;
    integer fcodes, flog, nsamp, start, nstream;
    integer n_wrap = 0;
    integer cidx = 0;                  // frames since the RESET_N release
    integer n_in = 0;                  // CIC inputs since the release
    integer n_in_bad = 0;
    integer cg;
    logic [4:0] nxt = 5'd16;           // the code of the coming e2 (the stream's next byte)
    function automatic integer next_byte();
        integer b;
        b = $fgetc(fcodes);
        if (b < 0) begin                 // the end of the stream: wrap
            void'($fseek(fcodes, 0, 0));
            b = $fgetc(fcodes);
            n_wrap = n_wrap + 1;
        end
        return b;
    endfunction
    initial begin
        if (!$value$plusargs("codes=%s", codes_file)) begin $display("FAIL: tb_e2e_r15 needs +codes=<file>"); $finish; end
        if (!$value$plusargs("log=%s", log_file)) log_file = "build/e2e_r15.log";
        if (!$value$plusargs("nsamp=%d", nsamp)) nsamp = 20;
        if (!$value$plusargs("start=%d", start)) start = 0;
        fcodes = $fopen(codes_file, "rb");
        if (fcodes == 0) begin $display("FAIL: cannot open %s", codes_file); $finish; end
        void'($fseek(fcodes, 0, 2));
        nstream = $ftell(fcodes);
        void'($fseek(fcodes, start % nstream, 0));
        flog = $fopen(log_file, "w");
        $fdisplay(flog, "# tb_e2e_r15 codes %s start %0d nstream %0d nsamp %0d", codes_file, start, nstream, nsamp);
        cg = next_byte();
        nxt = cg[4:0];
    end
    always @(posedge MCLK) begin
        // the CIC takes CODE at cic_en (frame cycle 3): input n_in is the code set at this frame's cycle 1
        if (RESET_N && dut.cic_en) begin
            if (n_in !== cidx - 1) begin
                n_in_bad = n_in_bad + 1;
                if (n_in_bad <= 5) fail($sformatf("CIC input %0d taken in frame %0d (one input per frame expected)", n_in, cidx - 1));
            end
            n_in = n_in + 1;
        end
        if (dut.cycle == 5'd1 && RESET_N) begin   // CODE changes at e2, as eeg_adc_dig's
            if (cg < 0 || cg > 31) fail($sformatf("stream byte %0d at position %0d", cg, start + cidx));
            CODE <= nxt;
            cidx <= cidx + 1;
            cg = next_byte();
            nxt <= cg[4:0];
        end
    end

    // ---------------- the armed clear (ALIGN) at an output, pushes, drops
    logic cic_clear_taken = 1'b0;
    always @(posedge MCLK) if (dut.u_cic.step[3]) cic_clear_taken <= dut.u_cic.arm;
    integer n_out = 0, n_clear = 0, n_push = 0, n_drop = 0;
    logic [15:0] last_seq;
    logic [23:0] last_data;
    logic [7:0]  last_st;
    logic        last_v = 1'b0;
    always @(posedge MCLK) begin
        if (RESET_N && dut.cic_stb) begin
            n_out = n_out + 1;
            if (cic_clear_taken) begin
                n_clear = n_clear + 1;
                $fdisplay(flog, "C %0d %0d", dut.seq_cnt, n_in);
            end
        end
        if (dut.ovr_set) n_drop = n_drop + 1;
        if (dut.apply)                last_v <= 1'b0;
        else if (dut.u_fifo.push) begin
            n_push = n_push + 1;
            last_v <= 1'b1; last_seq <= dut.seq_cnt; last_data <= dut.cic_data; last_st <= dut.smp_status;
        end
        if (dut.seq_flush) last_v <= 1'b0;
    end

    // ---------------- LATEST: 8 bytes, CRC from LAT_HDR; re-read if an output was stored during the read
    integer n_lat = 0, n_lat_reread = 0;
    task automatic lat_check();
        logic [7:0] c, st;
        logic [15:0] sq;
        logic [23:0] d;
        integer p0, lv0, tries;
        logic v; logic [15:0] es; logic [23:0] ed; logic [7:0] est;
        tries = 0;
        do begin
            p0 = n_push;
            lv0 = dut.fifo_level;
            v = last_v; es = last_seq; ed = last_data; est = last_st;
            spi_tx[0] = LAT_HDR;
            for (int i = 1; i < SMP_FRAME_LEN; i++) spi_tx[i] = 8'h00;
            spi_xfer(SMP_FRAME_LEN, 0);
            tries = tries + 1;
            if (n_push != p0) n_lat_reread = n_lat_reread + 1;
        end while (n_push != p0 && tries < 3);
        st = spi_rx[SMP_BYTE_SSTAT];
        sq = {spi_rx[SMP_BYTE_SEQ], spi_rx[SMP_BYTE_SEQ + 1]};
        d  = {spi_rx[SMP_BYTE_DATA], spi_rx[SMP_BYTE_DATA + 1], spi_rx[SMP_BYTE_DATA + 2]};
        c  = tb_crc8_update(8'h00, LAT_HDR);
        for (int i = 1; i < SMP_BYTE_CRC; i++) c = tb_crc8_update(c, spi_rx[i]);
        checks = checks + 1;
        n_lat = n_lat + 1;
        if (c !== spi_rx[SMP_BYTE_CRC]) fail("LATEST: CRC wrong");
        if (!v) fail("LATEST read with no stored output");
        else if (sq !== es || d !== ed || st !== est)
            fail($sformatf("LATEST: status %02h SEQ %0d DATA %06h, the last stored output %02h %0d %06h", st, sq, d, est, es, ed));
        if (dut.fifo_level !== 8'(lv0) && n_push == p0)
            fail($sformatf("LATEST read changed FIFO_LEVEL %0d -> %0d", lv0, dut.fifo_level));
    endtask

    // ---------------- the host
    logic [7:0] v, st;
    logic [15:0] sq;
    logic [23:0] d;
    bit ok;
    integer nread = 0, prev_seq = -1, skip, k, n_burst = 0, max_queue = 0, n_poll = 0;
    real t_run, t0;
    task automatic read_one();
        r14_sample(st, sq, d, ok);
        checks = checks + 1;
        if (!ok) fail($sformatf("sample %0d: CRC wrong", nread));
        if (st !== 8'h80) fail($sformatf("sample %0d (SEQ %0d): status 0x%02h, expected VALID alone (0x80)", nread, sq, st));
        if (prev_seq >= 0 && sq !== 16'(prev_seq + 1))
            fail($sformatf("sample %0d: SEQ %0d after %0d", nread, sq, prev_seq));
        $fdisplay(flog, "S %0d %06h %02h", sq, d, st);
        prev_seq = sq;
        nread = nread + 1;
    endtask

    initial begin
        #1;
        repeat (20) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (200) @(negedge MCLK);
        r14_read(A_ID, v);       expect8(v, ID_ID_RST, "ID");
        r14_read(A_VERSION, v);  expect8(v, 8'h11, "VERSION");
        r14_read(A_CAPS, v);     expect8(v, 8'h18, "CAPS (FIFO depth 8, CRC)");
        r14_write(A_IF_CFG, 8'h01);
        bfm_crc_en = 1'b1;
        r14_read(A_IF_CFG, v);   expect8(v, 8'h01, "IF_CFG with CRC");
        r14_read(A_ERR, v);      expect8(v, 8'h01, "ERR after reset (RESET_FLAG)");
        r14_write(A_ERR, 8'hFF);
        r14_read(A_ERR, v);      expect8(v, 8'h00, "ERR after its W1C");
        r14_cmd(CMD_START);
        t0 = $realtime;
        do begin
            #(250.0e3);
            @(negedge MCLK);
            r14_read(A_STATE, v);
            n_poll = n_poll + 1;
        end while (v[3:0] !== ST_RUN && $realtime - t0 < 100.0e6);
        if (v[3:0] !== ST_RUN) begin fail("not in RUN 100 ms after START"); $finish; end
        t_run = $realtime;
        $display("RUN %0.3f ms after START (%0d STATE polls); the armed clears so far: %0d", (t_run - t0) / 1.0e6, n_poll, n_clear);
        r14_read(A_CFG_GEN, v);  expect8(v, 8'h01, "CFG_GEN after START");
        // level mode (the default): read while DRDY_N is Low (it rises at most 5 MCLK after the CS_N rise of the read
        // that empties the FIFO; spi_xfer ends 600 ns after that rise)
        while (nread < nsamp / 2) begin
            if (DRDY_N !== 1'b0) @(negedge DRDY_N);
            @(negedge MCLK);
            if (nread % 97 == 50) begin
                // a backlog: let 1..6 more outputs be stored (1 ms each), then read the queue in a row
                skip = 1 + (n_burst % 6);
                n_burst = n_burst + 1;
                #(skip * 1.0e6 + 0.1e6);
                @(negedge MCLK);
                if (dut.fifo_level > max_queue) max_queue = dut.fifo_level;
                checks = checks + 1;
                if (dut.fifo_level !== 8'(skip + 1)) fail($sformatf("FIFO_LEVEL %0d after %0d outputs unread", dut.fifo_level, skip + 1));
            end
            while (DRDY_N === 1'b0) begin
                read_one();
                if (nread % 64 == 0) lat_check();
                if (nread % 1000 == 0)
                    $display("  %0d samples, stream position %0d, %0d errors", nread, start + cidx, errors);
            end
        end
        // pulse mode: one read per 128-MCLK pulse
        r14_write(A_IF_CFG, 8'h03);
        r14_read(A_IF_CFG, v);   expect8(v, 8'h03, "IF_CFG: pulse mode, CRC");
        while (nread < nsamp) begin
            @(negedge DRDY_N);
            @(negedge MCLK);
            if (nread % 97 == 50 && nread + 8 < nsamp) begin
                skip = 1 + (n_burst % 6);
                n_burst = n_burst + 1;
                repeat (skip) @(negedge DRDY_N);
                @(negedge MCLK);
                if (dut.fifo_level > max_queue) max_queue = dut.fifo_level;
                checks = checks + 1;
                if (dut.fifo_level !== 8'(skip + 1)) fail($sformatf("FIFO_LEVEL %0d after %0d pulses unread", dut.fifo_level, skip + 1));
                for (k = 0; k <= skip; k++) read_one();
            end else begin
                read_one();
            end
            if (nread % 64 == 0) lat_check();
            if (nread % 1000 == 0)
                $display("  %0d samples, stream position %0d, %0d errors", nread, start + cidx, errors);
        end
        r14_cmd(CMD_STOP);
        repeat (200) @(negedge MCLK);
        r14_read(A_STATE, v);    expect8(v, {4'h0, ST_IDLE}, "STATE after STOP");
        r14_read(A_DFLAG, v);    expect8(v, 8'h00, "DFLAG at the end");
        r14_read(A_ERR, v);      expect8(v, 8'h00, "ERR at the end");
        r14_read(A_DROP_CNT, v); expect8(v, 8'h00, "DROP_CNT at the end");
        r14_read(A_CFG_GEN, v);  expect8(v, 8'h01, "CFG_GEN at the end");
        checks = checks + 3;
        if (n_drop != 0) fail($sformatf("%0d FIFO drops", n_drop));
        if (n_in_bad != 0) fail($sformatf("%0d CIC inputs off their frames", n_in_bad));
        if (n_clear != 1) fail($sformatf("%0d armed clears, expected 1 (ALIGN)", n_clear));
        $fdisplay(flog, "E samples %0d frames %0d inputs %0d outputs %0d wraps %0d errors %0d spi_errors %0d", nread, cidx,
                  n_in, n_out, n_wrap, errors, spi_errors);
        $fclose(flog);
        $display("tb_e2e_r15: %0d samples read (%0d backlogs, queue up to %0d, %0d LATEST reads, %0d re-read), %0d frames of the stream from %0d (%0d wraps), %0d CIC inputs, %0d outputs, %0d pushes, %0d checks, %0d failures, %0d SPI errors (%0d transfers, MISO latency up to %0.1f ns)",
                 nread, n_burst, max_queue, n_lat, n_lat_reread, cidx, start, n_wrap, n_in, n_out, n_push, checks, errors,
                 spi_errors, spi_xfers, spi_miso_lat_max);
        if (errors == 0 && spi_errors == 0) $display("PASS: tb_e2e_r15 (the samples go to tb/check_e2e_r15.py)");
        else $display("FAIL: tb_e2e_r15");
        $finish;
    end
endmodule

`default_nettype wire
