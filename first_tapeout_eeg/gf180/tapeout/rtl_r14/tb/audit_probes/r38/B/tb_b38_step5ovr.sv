// audit round 38, auditor B: step 5 (i) of the host procedure with two aligned chips (shared MCLK and RESET_N, own
// CS_N and DRDY_N, CRC on), where chip B is left unread in RUN for N_WAIT output intervals before its round (a host
// that runs step 5's rounds one chip after another, or waits for another chip's RUN): the round reads A, B, A out to
// the empty word right after an output time and compares the last SEQ of B with A's, as step 5 (i) says. Every word
// is printed (SEQ, status byte, CRC check), then DFLAG of both chips (CRC read) and the next word of B.
`timescale 1ns / 1ps
`default_nettype none
module tb_b38_step5ovr;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    localparam real TH = 500.0;                         // SCLK half period: 1 MHz
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, MOSI = 1'b0;
    logic [1:0] CS_N = 2'b11;
    logic [4:0] CODE = 5'd16;
    wire  [1:0] MISO, MISO_OE, DRDY_N;
    wire  [1:0] RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN, CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT,
                CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire  [7:0] TEST_CFG [0:1];
    wire  [3:0] CPF_TRIM [0:1], OFEN [0:1];
    wire  [1:0] AFE_IBIAS [0:1], BTRIM_P [0:1], BTRIM_N [0:1];
    wire  [9:0] OFM [0:1];
    integer N_WAIT;
    genvar g;
    generate for (g = 0; g < 2; g++) begin : chip
        eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.MCLK(MCLK), .RESET_N(RESET_N), .SCLK(SCLK),
            .CS_N(CS_N[g]), .MOSI(MOSI), .MISO(MISO[g]), .MISO_OE(MISO_OE[g]), .DRDY_N(DRDY_N[g]),
            .RAW_DATA(RAW_DATA[g]), .RAW_CLK(RAW_CLK[g]), .ADC_RST_N(ADC_RST_N[g]), .TH_CAPTURE(TH_CAPTURE[g]),
            .DAC_LOAD(DAC_LOAD[g]), .DWA_EN(DWA_EN[g]), .CODE(CODE), .CMP_STROBE(CMP_STROBE[g]), .DAC_CLK(DAC_CLK[g]),
            .CHOP(CHOP[g]), .CHOP_OUT(CHOP_OUT[g]), .CHOP_BLANK(CHOP_BLANK[g]), .AFE_RST(AFE_RST[g]),
            .CHOP_EN(CHOP_EN[g]), .TEST_CFG(TEST_CFG[g]), .CPF_TRIM(CPF_TRIM[g]), .AFE_IBIAS(AFE_IBIAS[g]),
            .BTRIM_P(BTRIM_P[g]), .BTRIM_N(BTRIM_N[g]), .OFM(OFM[g]), .OFS(OFS[g]), .OFEN(OFEN[g]), .CHOP1(CHOP1[g]));
    end endgenerate
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    wire miso_bus = MISO_OE[0] ? MISO[0] : (MISO_OE[1] ? MISO[1] : 1'b1);    // pulled up (PIN-04)

    function automatic logic [7:0] crc8(input logic [7:0] c, input logic [7:0] d);
        logic [7:0] x; x = c ^ d;
        for (int i = 0; i < 8; i++) x = x[7] ? ((x << 1) ^ 8'h07) : (x << 1);
        return x;
    endfunction

    logic [7:0] tx [0:15], rx [0:15];
    task automatic xfer(input int c, input int nb);
        CS_N[c] = 1'b0; MOSI = tx[0][7];
        #1000.0;
        for (int n = 0; n < 8 * nb; n++) begin
            SCLK = 1'b1; rx[n / 8][7 - n % 8] = miso_bus; #TH;
            SCLK = 1'b0; MOSI = (n + 1 < 8 * nb) ? tx[(n + 1) / 8][7 - (n + 1) % 8] : 1'b0;
            if (n + 1 < 8 * nb) #TH;
        end
        #500.0; CS_N[c] = 1'b1; #1000.0;
    endtask
    task automatic wr(input int c, input logic [6:0] a, input logic [7:0] v, input bit crc);
        tx[0] = {1'b0, a}; tx[1] = v; tx[2] = crc8(crc8(8'h00, tx[0]), v);
        xfer(c, crc ? 3 : 2);
    endtask
    task automatic rd(input int c, input logic [6:0] a, output logic [7:0] v, output bit ok);
        tx[0] = {1'b1, a}; tx[1] = 0; tx[2] = 0;
        xfer(c, 3);
        v = rx[1]; ok = (rx[2] == crc8(crc8(8'h00, tx[0]), rx[1])) && rx[0][7:6] == 2'b10;
    endtask
    // one sample read (8 bytes): returns the word and whether its CRC holds
    task automatic smp(input int c, output logic [7:0] hdr, output logic [7:0] st, output logic [15:0] sq, output bit ok);
        logic [7:0] k;
        tx[0] = SMP_HDR; for (int i = 1; i < 8; i++) tx[i] = 0;
        xfer(c, 8);
        k = crc8(8'h00, SMP_HDR); for (int i = 1; i < 7; i++) k = crc8(k, rx[i]);
        hdr = rx[0]; st = rx[1]; sq = {rx[2], rx[3]}; ok = (k == rx[7]);
    endtask
    // read a chip out to the CRC-valid empty word whose header has DATA = 0 (step 6's stop rule); last VALID SEQ
    task automatic drain(input int c, input string tag, input bit show, output int nwords, output int last);
        logic [7:0] h, s; logic [15:0] q; bit ok;
        nwords = 0; last = -1;
        forever begin
            smp(c, h, s, q, ok);
            if (!ok) begin $display("  %s chip %0d: CRC error", tag, c); continue; end
            if (s[SMP_VALID_LSB]) begin
                nwords++; last = q;
                if (show) $display("  %s chip %0d word %0d: SEQ %0d status 0x%02h (OVERRUN %0d)", tag, c, nwords, q, s,
                                   s[SMP_OVERRUN_LSB]);
            end else if (h[7:6] == 2'b10 && !h[STATUS_DATA_LSB]) break;
        end
    endtask

    int na, nb, la, lb, la2, n_a2;
    logic [7:0] v, h, s; logic [15:0] q; bit ok;
    initial begin
        if (!$value$plusargs("wait=%d", N_WAIT)) N_WAIT = 12;
        #2000.0 RESET_N = 1'b1;
        #2000.0;
        for (int c = 0; c < 2; c++) begin
            wr(c, A_IF_CFG, 8'h01, 0);                  // step 3: CRC on (level mode)
            wr(c, A_ERR, 8'h01, 1);                     // RESET_FLAG cleared
            wr(c, A_ALERT_MASK_D, 8'h00, 1);
        end
        for (int c = 0; c < 2; c++) wr(c, A_COMMAND, CMD_START, 1);
        wait (chip[0].dut.seq_state == ST_RUN && chip[1].dut.seq_state == ST_RUN);
        $display("both chips in RUN at %0.3f ms", $realtime / 1e6);
        // chip A drained after every output (the reference, read in every round); chip B left for N_WAIT intervals
        for (int i = 0; i < N_WAIT; i++) begin
            @(negedge DRDY_N[0]); #2000.0;
            drain(0, "A", 0, na, la);
        end
        // step 5 (i): right after an output time, A, B, A read out; compare B's last SEQ with A's last
        @(negedge DRDY_N[0]); #2000.0;
        $display("round (i) at %0.3f ms: FIFO_LEVEL of B before = %0d (DFLAG.OVERRUN %0d)", $realtime / 1e6,
                 chip[1].dut.fifo_level, chip[1].dut.dflag_overrun);
        drain(0, "A1", 1, na, la);
        drain(1, "B", 1, nb, lb);
        drain(0, "A2", 1, n_a2, la2);
        $display("round (i): A last SEQ %0d (%0d words), B last SEQ %0d (%0d words), A's second read-out %0d new words",
                 la, na, lb, nb, n_a2);
        $display("step 5 (i) compares %0d with %0d: %s", lb, la, (lb == la) ? "equal" : "DIFFERENT -> common RESET_N");
        rd(0, A_DFLAG, v, ok); $display("DFLAG A 0x%02h (crc ok %0d)", v, ok);
        rd(1, A_DFLAG, v, ok); $display("DFLAG B 0x%02h (crc ok %0d)", v, ok);
        @(negedge DRDY_N[1]); #2000.0;
        smp(1, h, s, q, ok);
        $display("next word of B: SEQ %0d status 0x%02h (OVERRUN %0d) crc ok %0d", q, s, s[SMP_OVERRUN_LSB], ok);
        $finish;
    end
    initial begin #80_000_000; $display("TIMEOUT"); $finish; end
endmodule
`default_nettype wire
