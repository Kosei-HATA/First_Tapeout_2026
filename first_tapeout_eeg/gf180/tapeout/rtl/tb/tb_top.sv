// tb_top - integrated test of eeg_digital_top with a sigma-delta code stream.
//
// * TH[30:0] emulates the quantizer: for frame f the thermometer of code c[f]
//   is driven only from the middle of frame cycle 1 to the middle of cycle 2
//   (around the capture edge e2); random bits otherwise. A capture at any
//   other edge would therefore corrupt the results.
// * Before the start command the codes walk through 0..31 (pre-roll). The
//   start command (CONTROL = RUN | FILTER_CLEAR | DWA_EN | RAW_EN | CHOP_EN)
//   is aligned so that the clear lands mid-frame; from the next frame on TH
//   carries build/top_stream.codes (model/sdm2_model.py) from index 0.
//   CHOP_FAST stays at its default (128 kHz chop) in every CONTROL write.
// * Every sample read over SPI (2 MHz, whenever DRDY_N is low) is compared
//   bit-exactly with build/top_stream.gold (model/cic_golden.py on the same
//   stream): STATUS = 0x80, SEQ = 0, 1, 2, ..., CRC.
// * SEL1/SEL2 are compared at every dac_load edge with a reference DWA model
//   (k = 31 - c of the same frame; DWA_EN is switched off and on again
//   during the run). SEL may only change at the dac_load edge, i.e.
//   (DAC_LOAD_CYCLE + 1) MCLK after the CMP_STROBE rising edge.
// * RAW_DATA/RAW_CLK: each frame carries {101, c of the previous frame},
//   8 RAW_CLK rising edges per frame; quiet when RAW_EN = 0.
// * CHOP edges coincide with CMP_STROBE rising edges, and every CHOP phase is
//   128 MCLK (128 kHz).
// * CHOP_BLANK (default BLANK_LEN = 7): high from 1 MCLK before to 7 MCLK
//   after every CHOP_OUT edge (except the one at the first MCLK edge after
//   reset), and no other pulses.
// Parameters: DLC (DAC_LOAD_CYCLE), NSAMP (number of samples to read).
`timescale 1ns / 1ps

module tb_top;

    parameter int DLC   = 2;
    parameter int NSAMP = 40;

    localparam real TMCLK = 30.5176;           // 32.768 MHz
    localparam int  NCODES = 60000;

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

    eeg_digital_top #(.DAC_LOAD_CYCLE(DLC)) dut (
        .MCLK (MCLK), .RESET_N (RESET_N),
        .SCLK (SCLK), .CS_N (CS_N), .MOSI (MOSI), .MISO (MISO), .MISO_OE (MISO_OE),
        .DRDY_N (DRDY_N), .RAW_DATA (RAW_DATA), .RAW_CLK (RAW_CLK),
        .TH (TH), .SEL1 (SEL1), .SEL2 (SEL2), .CMP_STROBE (CMP_STROBE),
        .CHOP (CHOP), .CHOP_OUT (CHOP_OUT), .CHOP_BLANK (CHOP_BLANK),
        .AFE_RST (AFE_RST), .CHOP_EN (CHOP_EN),
        .TEST_CFG (TEST_CFG), .CPF_TRIM (CPF_TRIM), .AFE_IBIAS (AFE_IBIAS),
        .BTRIM_P (BTRIM_P), .BTRIM_N (BTRIM_N), .OFM (OFM), .OFS (OFS), .OFEN (OFEN)
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
        logic [30:0] m;
        m = '0;
        for (int j = 0; j < k; j++) m[(p + j) % 31] = 1'b1;
        return m;
    endfunction

    // ------------------------------------------------------------------
    // stimulus and golden data
    // ------------------------------------------------------------------
    logic [7:0]  codes [0:NCODES-1];
    logic [23:0] gold  [0:255];
    integer      fd;
    integer      nread;

    integer f_align = -1;                      // first frame carrying codes[0]
    integer code_hist [0:1023];                // code applied in frame f (f mod 1024)
    integer seed = 99;
    real    t_cmp = 0.0;                       // last CMP_STROBE rising edge

    function automatic integer code_for_frame(input integer f);
        if (f_align >= 0 && f >= f_align) begin
            if (f - f_align < NCODES) return codes[f - f_align];
            return 15;
        end
        return (7 * f + 3) % 32;               // pre-roll: all codes 0..31
    endfunction

    // comparator emulation
    integer pipe_checks = 0;
    always @(posedge CMP_STROBE) begin
        integer c;
        t_cmp = $realtime;
        // loop delay: at the comparator strobe of frame n+1 the DACs carry
        // k = 31 - c[n] (decided one frame earlier, applied ELD after its strobe)
        if (f_cur >= 0) begin
            pipe_checks = pipe_checks + 1;
            if (popc(SEL1) != 31 - code_hist[f_cur % 1024] || popc(SEL2) != 31 - code_hist[f_cur % 1024])
                err("popcount(SEL) at CMP_STROBE != 31 - c of the previous frame");
        end
        f_cur = f_cur + 1;
        c = code_for_frame(f_cur);
        code_hist[f_cur % 1024] = c;
        TH = $random(seed);
        #(1.5 * TMCLK);
        TH = therm(c);                         // valid around the capture edge e2
        #(1.0 * TMCLK);
        TH = $random(seed);
    end

    // the first input accepted after FILTER_CLEAR is the next frame's
    always @(posedge MCLK) begin
        if (dut.filter_clear) begin
            if (dut.u_clkgen.cycle < 3) err("FILTER_CLEAR before cic_en: stream alignment would be lost");
            f_align = f_cur + 1;
        end
    end

    // ------------------------------------------------------------------
    // SEL1/SEL2 against a reference DWA model
    // ------------------------------------------------------------------
    integer p_ref = 0;
    integer sel_checks = 0;
    integer sel_dwa = 0;
    integer sel_therm = 0;
    real    t_load = -1.0;
    real    eld_min = 1.0e9;
    real    eld_max = 0.0;

    always @(posedge MCLK) begin
        if (dut.rst_n && dut.u_clkgen.dac_load) begin
            integer      k;
            logic        en;
            logic [30:0] exp;
            k  = 31 - code_hist[f_cur % 1024];
            en = dut.dwa_en;                   // value used by the DUT at this edge
            t_load = $realtime;
            if (en) begin
                exp   = run_mask(p_ref, k);
                p_ref = (p_ref + k) % 31;
                sel_dwa = sel_dwa + 1;
            end else begin
                exp = therm(k);
                sel_therm = sel_therm + 1;
            end
            #1.0;
            sel_checks = sel_checks + 1;
            if (SEL1 !== exp || SEL2 !== exp)
                err($sformatf("SEL1=%08h SEL2=%08h expected %08h (k=%0d dwa_en=%0d)", SEL1, SEL2, exp, k, en));
        end
    end

    always @(SEL1 or SEL2) begin
        if (dut.rst_n) begin
            if ($realtime != t_load) err("SEL changed outside a dac_load edge");
            if ($realtime - t_cmp < eld_min) eld_min = $realtime - t_cmp;
            if ($realtime - t_cmp > eld_max) eld_max = $realtime - t_cmp;
        end
    end

    // CHOP edges coincide with CMP_STROBE rising edges; 128 MCLK phases
    integer chop_edges = 0;
    real    t_chop_edge = -1.0;
    always @(CHOP) begin
        if (dut.rst_n) begin
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

    // CHOP_BLANK (default BLANK_LEN = 7): from 1 MCLK before to 7 MCLK after
    // every CHOP_OUT edge; the edge at the first MCLK edge after reset is exempt
    integer blank_pulses = 0;
    integer out_edges = 0;
    real    t_out_edge = -1.0;
    real    t_blank_rise = -1.0;
    always @(CHOP_OUT) begin
        if (dut.rst_n === 1'b1) begin
            out_edges = out_edges + 1;
            t_out_edge = $realtime;
            if (out_edges > 1) begin
                if (CHOP_BLANK !== 1'b1 || $realtime - t_blank_rise < 0.5 * TMCLK || $realtime - t_blank_rise > 1.5 * TMCLK)
                    err("CHOP_BLANK did not rise one MCLK before the CHOP_OUT edge");
            end
        end
    end
    always @(posedge CHOP_BLANK) if (dut.rst_n === 1'b1) t_blank_rise = $realtime;
    always @(negedge CHOP_BLANK) begin
        if (dut.rst_n === 1'b1) begin
            if ($realtime - t_blank_rise < 7.5 * TMCLK || $realtime - t_blank_rise > 8.5 * TMCLK)
                err($sformatf("CHOP_BLANK pulse of %0.1f ns, expected 8 MCLK", $realtime - t_blank_rise));
            if ($realtime - t_out_edge < 6.5 * TMCLK || $realtime - t_out_edge > 7.5 * TMCLK)
                err($sformatf("CHOP_BLANK fell %0.1f ns after the CHOP_OUT edge, expected 7 MCLK", $realtime - t_out_edge));
            blank_pulses = blank_pulses + 1;
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
    bit          ok;
    integer      ncompared = 0;
    integer      ngold = 0;
    integer      raw_quiet_errs = 0;

    initial begin
        fd = $fopen("build/top_stream.codes", "rb");
        if (fd == 0) begin
            $display("FAIL: tb_top (cannot open build/top_stream.codes)");
            $finish;
        end
        nread = $fread(codes, fd);
        $fclose(fd);
        if (nread != NCODES) err($sformatf("read %0d codes", nread));
        fd = $fopen("build/top_stream.gold", "r");
        if (fd == 0) begin
            $display("FAIL: tb_top (cannot open build/top_stream.gold)");
            $finish;
        end
        while (ngold < 256 && $fscanf(fd, "%h\n", gold[ngold]) == 1) ngold = ngold + 1;
        $fclose(fd);
        if (ngold < NSAMP) err($sformatf("only %0d golden samples", ngold));

        #200.0;
        if (SEL1 !== 31'h0000_FFFF || SEL2 !== 31'h0000_FFFF) err("SEL reset state");
        RESET_N = 1'b1;
        #3000.0;
        spi_half = 250.0;

        // AFE out of reset, DWA, RAW output, chopper at 128 kHz; not running yet
        spi_write_reg(8'h02, 8'h6C);
        #60000.0;                              // pre-roll frames (all codes, both DWA paths)

        // start: RUN | FILTER_CLEAR | DWA_EN | RAW_EN | CHOP_EN | CHOP_FAST,
        // CS_N released in frame cycle 8
        spi_tx[0] = 8'h20;
        spi_tx[1] = 8'h02;
        spi_tx[2] = 8'h6F;
        spi_cs_hold = 1'b1;
        fork
            spi_xfer(3, 0);
            begin
                wait (spi_cs_waiting);
                do @(negedge MCLK); while (dut.u_clkgen.cycle != 5'd8);
                spi_cs_hold = 1'b0;
            end
        join
        if (f_align < 0) err("FILTER_CLEAR not seen");

        for (int s = 0; s < NSAMP; s++) begin
            wait_drdy(s == 0 ? 3500.0 : 1500.0);   // the first valid output comes 3 periods after the clear
            spi_read_sample(st, sq, dt, ok);
            ncompared = ncompared + 1;
            if (!ok) err($sformatf("sample %0d: CRC mismatch", s));
            if (st !== 8'h80) err($sformatf("sample %0d: STATUS 0x%02h", s, st));
            if (sq !== s[15:0]) err($sformatf("sample %0d: SEQ %0d", s, sq));
            if (dt !== gold[s]) err($sformatf("sample %0d: DATA 0x%06h expected 0x%06h", s, dt, gold[s]));
            if (s == NSAMP / 3)     spi_write_reg(8'h02, 8'h69);   // DWA_EN = 0 (thermometer)
            if (s == 2 * NSAMP / 3) spi_write_reg(8'h02, 8'h6D);   // DWA_EN = 1
        end

        // RAW_EN = 0: after the current word RAW_CLK and RAW_DATA stay low
        spi_write_reg(8'h02, 8'h65);
        repeat (2) @(posedge CMP_STROBE);
        repeat (64) begin
            @(negedge MCLK);
            if (RAW_CLK !== 1'b0 || RAW_DATA !== 1'b0) raw_quiet_errs = raw_quiet_errs + 1;
        end
        if (raw_quiet_errs != 0) err("RAW_CLK/RAW_DATA active with RAW_EN = 0");

        if (sel_dwa < 1000 || sel_therm < 1000) err("too few SEL checks in one of the DWA modes");
        if (dut.chop_fast !== 1'b1) err("CHOP_FAST changed");
        if (blank_pulses < out_edges - 2 || blank_pulses > out_edges - 1) err($sformatf("%0d CHOP_BLANK pulses for %0d CHOP_OUT edges", blank_pulses, out_edges));
        if (raw_words < 1000) err("too few RAW words");
        if (errors == 0 && spi_errors == 0)
            $display("PASS: tb_top DAC_LOAD_CYCLE=%0d (%0d samples bit-exact vs golden, %0d SEL checks [%0d DWA, %0d thermometer], %0d SEL popcount checks at the next CMP_STROBE, ELD CMP_STROBE->SEL %0.2f..%0.2f ns, %0d RAW words, %0d CHOP edges at 128 kHz, %0d CHOP_BLANK pulses from 1 MCLK before to 7 MCLK after the CHOP_OUT edge, max MISO latency %0.1f ns)",
                     DLC, ncompared, sel_checks, sel_dwa, sel_therm, pipe_checks, eld_min, eld_max, raw_words, chop_edges, blank_pulses, spi_miso_lat_max);
        else
            $display("FAIL: tb_top DAC_LOAD_CYCLE=%0d (%0d errors, %0d SPI monitor errors)", DLC, errors, spi_errors);
        $finish;
    end

    // watchdog
    initial begin
        #((NSAMP + 10) * 1.1e6);
        $display("FAIL: tb_top (timeout)");
        $finish;
    end

endmodule
