// tb_e2e - end-to-end bit-true test of eeg_digital_sys with a long code stream from
// the CT sigma-delta behavioral loop (model/ct2_codes.py), checked at the ports.
//
// * TH[30:0] emulates the quantizer as in tb_top: for frame f the thermometer of
//   the frame's code is driven only from the middle of frame cycle 1 to the middle
//   of cycle 2 (around the capture edge e2), random bits otherwise.
// * After reset and a pre-roll (codes 0..31), the start command (CONTROL = RUN |
//   FILTER_CLEAR | DWA_EN | RAW_EN | CHOP_EN | CHOP_FAST, AFE_RST = 0) is released in
//   frame cycle 8, so the clear lands in that frame; from the next frame on TH
//   carries the stream (+codes) from index 0, read one byte per frame.
// * Every sample read over SPI (2 MHz, whenever DRDY_N is low) must equal the next
//   line of +gold (model/cic_golden.py on the same stream): STATUS = 0x80 (valid,
//   no overrun), SEQ = 0, 1, 2, ..., CRC. With +out the samples are also written
//   as "<seq> <data hex>" lines for the spectrum (model/e2e_spectrum.py).
// * Every frame, from the ports only: SEL1/SEL2 against a reference DWA model
//   (k = 31 - c, pointer from reset), popcount(SEL) = 31 - c of the previous frame
//   at the next CMP_STROBE, SEL changing only (DAC_LOAD_CYCLE + 1) MCLK after the
//   CMP_STROBE rising edge, DAC_CLK one MCLK later and one MCLK wide, the RAW word
//   {101, c of the previous frame}, CHOP edges on CMP_STROBE with 128-MCLK phases,
//   CHOP_BLANK from 1 MCLK before to 7 MCLK after every CHOP_OUT edge, and CHOP1
//   (4 kHz) edges at e16 every 128 frames.
// * Gate level: compile tb/gl_shadow.sv as a second root (+define+TB=tb_e2e) to run
//   the LibreLane netlists in lockstep with this design under test (run_e2e.sh --gl).
//
// Plusargs: +codes=<file> +gold=<file> +nsamp=<n> [+out=<file>]
`timescale 1ns / 1ps

module tb_e2e;

    parameter int DLC = 2;

    localparam real TMCLK = 30.5176;           // 32.768 MHz

    logic        MCLK = 1'b0;
    logic        RESET_N = 1'b0;
    logic        SCLK = 1'b0;
    logic        CS_N = 1'b1;
    logic        MOSI = 1'b0;
    logic [30:0] TH = '0;
    wire         MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK;
    wire  [30:0] SEL1, SEL2;
    wire         CMP_STROBE, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN;
    wire  [7:0]  TEST_CFG;
    wire  [3:0]  CPF_TRIM;
    wire  [1:0]  AFE_IBIAS;
    wire  [1:0]  BTRIM_P;
    wire  [1:0]  BTRIM_N;
    wire  [9:0]  OFM;
    wire         OFS;
    wire  [3:0]  OFEN;
    wire         CHOP1;
    wire         DAC_CLK;

    eeg_digital_sys #(.DAC_LOAD_CYCLE(DLC)) dut (
        .MCLK (MCLK), .RESET_N (RESET_N),
        .SCLK (SCLK), .CS_N (CS_N), .MOSI (MOSI), .MISO (MISO), .MISO_OE (MISO_OE),
        .DRDY_N (DRDY_N), .RAW_DATA (RAW_DATA), .RAW_CLK (RAW_CLK),
        .TH (TH), .SEL1 (SEL1), .SEL2 (SEL2), .CMP_STROBE (CMP_STROBE), .DAC_CLK (DAC_CLK),
        .CHOP (CHOP), .CHOP_OUT (CHOP_OUT), .CHOP_BLANK (CHOP_BLANK),
        .AFE_RST (AFE_RST), .CHOP_EN (CHOP_EN),
        .TEST_CFG (TEST_CFG), .CPF_TRIM (CPF_TRIM), .AFE_IBIAS (AFE_IBIAS),
        .BTRIM_P (BTRIM_P), .BTRIM_N (BTRIM_N), .OFM (OFM), .OFS (OFS), .OFEN (OFEN),
        .CHOP1 (CHOP1)
    );

    always #(TMCLK / 2.0) MCLK = ~MCLK;

    `include "spi_bfm.svh"

    integer errors = 0;
    integer f_cur = -1;                        // frame index (CMP_STROBE rising edges)

    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 20) $display("ERROR @%0t frame %0d: %s", $time, f_cur, msg);
    endtask

    function automatic logic [30:0] therm(input integer n);
        logic [30:0] v;
        v = '0;
        for (int i = 0; i < n; i++) v[i] = 1'b1;
        return v;
    endfunction

    function automatic integer popc(input logic [30:0] v);
        integer n;
        n = 0;
        for (int i = 0; i < 31; i++) n = n + v[i];
        return n;
    endfunction

    function automatic logic [30:0] run_mask(input integer p, input integer k);
        logic [30:0] msk;
        msk = '0;
        for (int j = 0; j < k; j++) msk[(p + j) % 31] = 1'b1;
        return msk;
    endfunction

    // ------------------------------------------------------------------
    // stimulus: the code stream, one byte per frame from f_align on
    // ------------------------------------------------------------------
    string  codes_file;
    string  gold_file;
    string  out_file;
    integer fc = 0;
    integer fg = 0;
    integer fo = 0;
    integer nsamp = 0;
    integer f_align = -1;                      // first frame carrying stream index 0
    integer n_stream = 0;                      // stream codes applied
    bit     stream_end = 1'b0;
    integer code_hist [0:1023];                // code applied in frame f (f mod 1024)
    integer code_count [0:31];
    integer seed = 2026;
    real    t_cmp = 0.0;                       // last CMP_STROBE rising edge

    task automatic next_code(input integer f, output integer c);
        integer ch;
        if (f_align >= 0 && f >= f_align) begin
            ch = $fgetc(fc);
            if (ch < 0 || ch > 31) begin
                if (!stream_end) err("code stream ended or holds a value > 31");
                stream_end = 1'b1;
                c = 15;
            end else begin
                n_stream = n_stream + 1;
                code_count[ch] = code_count[ch] + 1;
                c = ch;
            end
        end else begin
            c = (7 * f + 3) % 32;              // pre-roll: all codes 0..31
        end
    endtask

    // comparator emulation and the per-frame SEL checks
    integer p_ref = 0;
    integer pipe_checks = 0;
    integer sel_checks = 0;
    real    t_load = -1.0;
    always @(posedge CMP_STROBE) begin
        integer      c;
        integer      k;
        logic [30:0] exp;
        t_cmp = $realtime;
        // loop delay: at the strobe of frame n+1 the DACs carry k = 31 - c[n]
        if (f_cur >= 0) begin
            pipe_checks = pipe_checks + 1;
            if (popc(SEL1) != 31 - code_hist[f_cur % 1024] || popc(SEL2) != 31 - code_hist[f_cur % 1024])
                err("popcount(SEL) at CMP_STROBE != 31 - c of the previous frame");
        end
        f_cur = f_cur + 1;
        next_code(f_cur, c);
        code_hist[f_cur % 1024] = c;
        TH = $random(seed);
        #(1.5 * TMCLK);
        TH = therm(c);                         // valid around the capture edge e2
        #(1.0 * TMCLK);
        TH = $random(seed);
        // 1 ns after the SEL update edge e(DLC + 1): DWA_EN is 1 from reset on
        // (CONTROL reset 0x74, every write here keeps it), pointer from 0
        #((DLC + 1 - 2.5) * TMCLK + 1.0);
        k   = 31 - c;
        exp = run_mask(p_ref, k);
        p_ref = (p_ref + k) % 31;
        sel_checks = sel_checks + 1;
        if (SEL1 !== exp || SEL2 !== exp)
            err($sformatf("SEL1=%08h SEL2=%08h expected %08h (k=%0d)", SEL1, SEL2, exp, k));
    end

    // the clear (released in frame cycle 8) must land in the same frame, after cic_en
    integer clear_frame = -1;
    always @(posedge MCLK) begin
        if (dut.u_top.filter_clear) begin
            if (dut.u_top.u_clkgen.cycle < 3) err("FILTER_CLEAR before cic_en: stream alignment would be lost");
            clear_frame = f_cur;
        end
    end

    // SEL changes only at the update edge: (DLC + 1) MCLK after the CMP_STROBE rising edge
    integer sel_changes = 0;
    real    eld_min = 1.0e9;
    real    eld_max = 0.0;
    always @(SEL1 or SEL2) begin
        if (RESET_N === 1'b1 && f_cur >= 0) begin
            sel_changes = sel_changes + 1;
            if ($realtime - t_cmp < eld_min) eld_min = $realtime - t_cmp;
            if ($realtime - t_cmp > eld_max) eld_max = $realtime - t_cmp;
            if ($realtime - t_cmp < (DLC + 1) * TMCLK - 0.01 || $realtime - t_cmp > (DLC + 1) * TMCLK + 0.01)
                err($sformatf("SEL changed %0.3f ns after CMP_STROBE", $realtime - t_cmp));
            t_load = $realtime;
        end
    end

    // DAC_CLK: rises one MCLK after the SEL update edge, one MCLK wide
    integer dacclk_pulses = 0;
    real    t_dacclk_rise = -1.0;
    always @(DAC_CLK) begin
        if (RESET_N === 1'b1 && f_cur >= 0) begin
            if (DAC_CLK === 1'b1) begin
                dacclk_pulses = dacclk_pulses + 1;
                if ($realtime - t_cmp < (DLC + 2) * TMCLK - 0.01 || $realtime - t_cmp > (DLC + 2) * TMCLK + 0.01)
                    err($sformatf("DAC_CLK rose %0.3f ns after CMP_STROBE", $realtime - t_cmp));
                t_dacclk_rise = $realtime;
            end else if (t_dacclk_rise > 0.0) begin
                if ($realtime - t_dacclk_rise < TMCLK - 0.01 || $realtime - t_dacclk_rise > TMCLK + 0.01)
                    err("DAC_CLK pulse not one MCLK wide");
            end
        end
    end

    // CHOP edges coincide with CMP_STROBE rising edges; 128 MCLK phases
    integer chop_edges = 0;
    real    t_chop_edge = -1.0;
    always @(CHOP) begin
        if (RESET_N === 1'b1) begin
            #0.001;
            chop_edges = chop_edges + 1;
            if (CMP_STROBE !== 1'b1 || $realtime - t_cmp > 0.002) err("CHOP edge not at a CMP_STROBE edge");
            if (t_chop_edge > 0.0) begin
                if ($realtime - t_chop_edge < 127.5 * TMCLK || $realtime - t_chop_edge > 128.5 * TMCLK)
                    err($sformatf("CHOP phase of %0.1f ns, expected 128 MCLK", $realtime - t_chop_edge));
            end
            t_chop_edge = $realtime;
        end
    end

    // CHOP_BLANK (BLANK_LEN = 7): from 1 MCLK before to 7 MCLK after every CHOP_OUT
    // edge; the edge at the first MCLK edge after reset is exempt
    integer blank_pulses = 0;
    integer out_edges = 0;
    real    t_out_edge = -1.0;
    real    t_blank_rise = -1.0;
    always @(CHOP_OUT) begin
        if (RESET_N === 1'b1) begin
            out_edges = out_edges + 1;
            t_out_edge = $realtime;
            if (out_edges > 1) begin
                if (CHOP_BLANK !== 1'b1 || $realtime - t_blank_rise < 0.5 * TMCLK || $realtime - t_blank_rise > 1.5 * TMCLK)
                    err("CHOP_BLANK did not rise one MCLK before the CHOP_OUT edge");
            end
        end
    end
    always @(posedge CHOP_BLANK) if (RESET_N === 1'b1) t_blank_rise = $realtime;
    always @(negedge CHOP_BLANK) begin
        if (RESET_N === 1'b1) begin
            if ($realtime - t_blank_rise < 7.5 * TMCLK || $realtime - t_blank_rise > 8.5 * TMCLK)
                err($sformatf("CHOP_BLANK pulse of %0.1f ns, expected 8 MCLK", $realtime - t_blank_rise));
            if ($realtime - t_out_edge < 6.5 * TMCLK || $realtime - t_out_edge > 7.5 * TMCLK)
                err($sformatf("CHOP_BLANK fell %0.1f ns after the CHOP_OUT edge, expected 7 MCLK", $realtime - t_out_edge));
            blank_pulses = blank_pulses + 1;
        end
    end

    // CHOP1 (OTA1 chopper, 4 kHz after reset): edges only at e16, every 128 frames
    integer chop1_edges = 0;
    integer f_chop1 = -1;
    always @(CHOP1) begin
        if (RESET_N === 1'b1 && f_cur >= 0) begin
            chop1_edges = chop1_edges + 1;
            if ($realtime - t_cmp < 16.0 * TMCLK - 0.01 || $realtime - t_cmp > 16.0 * TMCLK + 0.01)
                err($sformatf("CHOP1 edge %0.3f ns after CMP_STROBE, expected 16 MCLK", $realtime - t_cmp));
            if (f_chop1 >= 0 && f_cur - f_chop1 != 128)
                err($sformatf("CHOP1 phase of %0d frames, expected 128 (4 kHz)", f_cur - f_chop1));
            f_chop1 = f_cur;
        end
    end

    // ------------------------------------------------------------------
    // RAW serializer receiver
    // ------------------------------------------------------------------
    integer     raw_frame = -1;
    integer     raw_nbits = 0;
    integer     raw_words = 0;
    logic [7:0] raw_word = 8'h00;

    always @(posedge RAW_CLK) begin
        if (f_cur != raw_frame) begin
            if (raw_frame >= 0 && raw_nbits != 8) err($sformatf("RAW: %0d bits in a frame", raw_nbits));
            raw_frame = f_cur;
            raw_nbits = 0;
        end
        raw_word  = {raw_word[6:0], RAW_DATA};
        raw_nbits = raw_nbits + 1;
        if (raw_nbits == 8) begin
            if (raw_word !== {3'b101, code_hist[(f_cur + 1023) % 1024][4:0]})
                err($sformatf("RAW word %02h expected %02h", raw_word, {3'b101, code_hist[(f_cur + 1023) % 1024][4:0]}));
            raw_words = raw_words + 1;
        end
    end

    // ------------------------------------------------------------------
    // main sequence
    // ------------------------------------------------------------------
    task automatic wait_drdy(input real timeout_us);
        real t0;
        t0 = $realtime;
        while (DRDY_N !== 1'b0 && ($realtime - t0) < timeout_us * 1000.0) #(500.0);
        if (DRDY_N !== 1'b0) err($sformatf("DRDY_N did not go low within %0.0f us", timeout_us));
    endtask

    logic [7:0]  st;
    logic [15:0] sq;
    logic [23:0] dt;
    logic [23:0] gd;
    bit          ok;
    integer      ncompared = 0;
    integer      nmatch = 0;
    integer      r;
    integer      ncodes_used = 0;
    integer      f_rel;

    initial begin
        for (int i = 0; i < 32; i++) code_count[i] = 0;
        if (!$value$plusargs("codes=%s", codes_file) || !$value$plusargs("gold=%s", gold_file) ||
            !$value$plusargs("nsamp=%d", nsamp)) begin
            $display("FAIL: tb_e2e (+codes, +gold and +nsamp are required)");
            $finish;
        end
        fc = $fopen(codes_file, "rb");
        fg = $fopen(gold_file, "r");
        if (fc == 0 || fg == 0) begin
            $display("FAIL: tb_e2e (cannot open %s or %s)", codes_file, gold_file);
            $finish;
        end
        if ($value$plusargs("out=%s", out_file)) fo = $fopen(out_file, "w");

        #200.0;
        if (SEL1 !== 31'h0000_FFFF || SEL2 !== 31'h0000_FFFF) err("SEL reset state");
        RESET_N = 1'b1;
        #3000.0;
        spi_half = 250.0;

        // AFE out of reset, DWA, RAW output, chopper at 128 kHz; not running yet
        spi_write_reg(8'h02, 8'h6C);
        #60000.0;                              // pre-roll frames (all codes 0..31)

        // start: RUN | FILTER_CLEAR | DWA_EN | RAW_EN | CHOP_EN | CHOP_FAST, CS_N
        // released in frame cycle 8 (CMP_STROBE is high in cycle 0)
        spi_tx[0] = 8'h20;
        spi_tx[1] = 8'h02;
        spi_tx[2] = 8'h6F;
        spi_cs_hold = 1'b1;
        fork
            spi_xfer(3, 0);
            begin
                wait (spi_cs_waiting);
                @(negedge MCLK);
                while (CMP_STROBE !== 1'b1) @(negedge MCLK);
                repeat (8) @(negedge MCLK);
                f_align = f_cur + 1;
                spi_cs_hold = 1'b0;
            end
        join
        #(64.0 * TMCLK);
        if (clear_frame != f_align - 1) err($sformatf("FILTER_CLEAR in frame %0d, expected %0d", clear_frame, f_align - 1));

        for (int s = 0; s < nsamp; s++) begin
            wait_drdy(s == 0 ? 3500.0 : 1500.0);   // the first valid output comes 3 periods after the clear
            spi_read_sample(st, sq, dt, ok);
            ncompared = ncompared + 1;
            r = $fscanf(fg, "%h\n", gd);
            if (r != 1) begin
                err($sformatf("sample %0d: no golden value left", s));
            end else if (dt !== gd) begin
                err($sformatf("sample %0d: DATA 0x%06h expected 0x%06h", s, dt, gd));
            end else begin
                nmatch = nmatch + 1;
            end
            if (!ok) err($sformatf("sample %0d: CRC mismatch", s));
            if (st !== 8'h80) err($sformatf("sample %0d: STATUS 0x%02h", s, st));
            if (sq !== s[15:0]) err($sformatf("sample %0d: SEQ %0d", s, sq));
            if (fo != 0) $fwrite(fo, "%0d %06h\n", sq, dt);
            if (s % 1000 == 999) $display("  %0d samples, %0d frames of the stream, %0d errors", s + 1, n_stream, errors);
        end

        repeat (2) @(posedge CMP_STROBE);
        if (DRDY_N !== 1'b1) err("FIFO not empty after the last read");
        if (stream_end) err("the code stream ran out before the last sample");
        for (int i = 0; i < 32; i++) if (code_count[i] > 0) ncodes_used = ncodes_used + 1;
        if (blank_pulses < out_edges - 2 || blank_pulses > out_edges - 1) err($sformatf("%0d CHOP_BLANK pulses for %0d CHOP_OUT edges", blank_pulses, out_edges));
        if (dacclk_pulses < sel_checks - 1 || dacclk_pulses > sel_checks) err($sformatf("%0d DAC_CLK pulses for %0d SEL checks", dacclk_pulses, sel_checks));
        if (chop1_edges < f_cur / 128 - 1) err($sformatf("only %0d CHOP1 edges in %0d frames", chop1_edges, f_cur));
        if (fo != 0) $fclose(fo);
        if (errors == 0 && spi_errors == 0)
            $display("PASS: tb_e2e (%0d samples bit-exact vs golden, STATUS/SEQ/CRC ok, %0d stream frames [%0d distinct codes], %0d frames in all, %0d SEL checks vs reference DWA, %0d SEL popcount checks, ELD CMP_STROBE->SEL %0.2f..%0.2f ns, %0d DAC_CLK pulses, %0d RAW words, %0d CHOP edges, %0d CHOP_BLANK pulses, %0d CHOP1 edges, max MISO latency %0.1f ns)",
                     nmatch, n_stream, ncodes_used, f_cur + 1, sel_checks, pipe_checks, eld_min, eld_max, dacclk_pulses, raw_words, chop_edges, blank_pulses, chop1_edges, spi_miso_lat_max);
        else
            $display("FAIL: tb_e2e (%0d errors, %0d SPI monitor errors, %0d of %0d samples matched)", errors, spi_errors, nmatch, ncompared);
        $finish;
    end

    // watchdog
    initial begin
        #1.0;
        while (nsamp == 0) #1000.0;
        #((nsamp + 10) * 1.1e6);
        $display("FAIL: tb_e2e (timeout)");
        $finish;
    end

endmodule
