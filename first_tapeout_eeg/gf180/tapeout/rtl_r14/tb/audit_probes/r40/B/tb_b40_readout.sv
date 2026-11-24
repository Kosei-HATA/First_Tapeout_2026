// tb_b40_readout - audit round 40, auditor B: step 5 (i)'s read-out word counts on the RTL (one chip, CRC on, level
// mode). After RUN: (1) the chip is read out at once after an output time (1 sample + the empty word); (2) it is left
// unread for FIFO_DEPTH - 1 output times (the most the round-39 duty allows) and read out right after the next output
// time; (3) it is left unread for FIFO_DEPTH + 1 output times (FIFO full, a store dropped) and read out. For each
// read-out: the VALID words, all words (with the terminating empty word), the last SEQ, DFLAG after it.
`timescale 1ns / 1ps
`default_nettype none
module tb_b40_readout;
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

    logic [7:0] v, sst; logic [15:0] sq; logic [23:0] dt; bit ok;
    integer depth;
    task automatic readout(input string tag);
        integer nvalid, nwords, nbad; logic [15:0] last;
        nvalid = 0; nwords = 0; nbad = 0; last = 16'hxxxx;
        forever begin
            r14_sample(sst, sq, dt, ok);
            nwords++;
            if (!ok) nbad++;
            if (ok && sst[SMP_VALID_LSB]) begin nvalid++; last = sq; end
            if (ok && !sst[SMP_VALID_LSB] && spi_status[STATUS_DATA_LSB] == 1'b0) break;
            if (nwords > 20) break;
        end
        r14_read(7'h07, v);
        $display("%s: %0d words (%0d VALID, %0d with a bad CRC), last SEQ %0d, FIFO_DEPTH %0d, DFLAG 0x%02h (OVERRUN %0d)",
                 tag, nwords, nvalid, nbad, last, depth, v, v[DFLAG_OVERRUN_LSB]);
        $display("    literal 5.4 (i) test 'no read-out returns FIFO_DEPTH words': %s;  VALID-word reading: %s",
                 (nwords == depth) ? "FAILS (round not counted)" : "passes",
                 (nvalid >= depth) ? "FAILS (round not counted)" : "passes");
        if (v[DFLAG_OVERRUN_LSB]) r14_write(7'h07, 8'h01);
    endtask
    // DRDY_N edges while the chip is left unread (level mode), and the longest time without an edge (step 6's
    // 2-ms rule: "約 2 ms の間 DRDY_N の縁がなければ FIFO_LEVEL を CRC 付きで読み、0 でなければ FIFO を読み切る")
    integer n_edges; real t_last_edge, longest_quiet;
    always @(DRDY_N) begin n_edges = n_edges + 1; if ($realtime - t_last_edge > longest_quiet) longest_quiet = $realtime - t_last_edge; t_last_edge = $realtime; end
    task automatic wait_outputs(input integer n);
        n_edges = 0; t_last_edge = $realtime; longest_quiet = 0.0;
        repeat (n) @(posedge dut.cic_stb);
        repeat (40) @(posedge MCLK);
        if ($realtime - t_last_edge > longest_quiet) longest_quiet = $realtime - t_last_edge;
        $display("    left unread for %0d output times: %0d DRDY_N edges, longest time without an edge %0.3f ms (DRDY_N %b)",
                 n, n_edges, longest_quiet / 1.0e6, DRDY_N);
    endtask
    initial begin
        #(200e6);
        $display("FAIL: watchdog");
        $finish;
    end
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;                     // CRC on (step 3)
        r14_read(7'h02, v); depth = v[3:0];                             // CAPS.FIFO_DEPTH (step 3)
        $display("CAPS 0x%02h: FIFO_DEPTH %0d", v, depth);
        r14_write(7'h09, 8'h00);                                         // ALERT_MASK_D 0 (step 3)
        r14_write(7'h52, 8'd29);
        r14_write(7'h10, 8'h11);                                         // START
        while (dut.seq_state !== ST_RUN) @(posedge MCLK);
        $display("RUN at %0.3f ms", $realtime / 1.0e6);
        wait_outputs(1);
        readout("(1) read right after each output time    ");
        wait_outputs(depth - 1);
        readout("(2) after FIFO_DEPTH - 1 unread outputs  ");
        wait_outputs(depth + 1);
        readout("(3) after FIFO_DEPTH + 1 unread outputs  ");
        $display("tb_b40_readout done: %0d SPI timing errors", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
