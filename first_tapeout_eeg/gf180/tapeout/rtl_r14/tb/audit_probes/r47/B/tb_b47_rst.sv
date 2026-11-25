// tb_b47_rst - audit round 47, auditor B probe: an unexpected RESET_N of one chip in RUN (CRC on, pulse mode)
// against the host's ordinary frames; derived from tb_b47_sclk (not part of the repository's benches).
// The four single SCLK faults of the slip model (regmap.slip_hazards: a missed pulse, an extra pulse in the low phase
// before pulse k, a bounce inside pulse k's high phase, pulses k and k+1 merged) at every pulse of an 8-byte CRC-on
// sample read in RUN, at 1 MHz. Requirements 5.4 step 6 relies on: the chip raises FRAME_ERR and does not pop in every
// such frame, the very next header (CS_N high 4 MCLK) shows ALERT 0 -> 1, and the host's slipped copy passes the
// sample CRC only rarely (step 6 quotes about 0.26 %).
`timescale 1ns / 1ps
`default_nettype none
module tb_b47_rst;
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
    wire #(15.0) miso_pin = MISO;
    wire #(15.0) oe_pin   = MISO_OE;
    wire miso_pad = oe_pin ? miso_pin : 1'b1;              // board pull-up (PIN-04)

    function automatic logic [7:0] crc8u(input logic [7:0] c0, input logic [7:0] d);
        logic [7:0] c; c = c0 ^ d;
        for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        return c;
    endfunction

    logic [7:0] tx [0:15], rx [0:15];
    // one frame: nbits host pulses at 1 MHz (500/500 ns); fault kind fk (-1 none, 0 missed, 1 extra before, 2 bounce,
    // 3 merge k,k+1) at host pulse fp; the host samples MISO at its own rising edges
    task automatic xfer(input integer nbytes, input integer fk, input integer fp, input real tidle);
        integer nb; nb = 8 * nbytes;
        CS_N = 1'b0; MOSI = tx[0][7];
        if (fk == 1 && fp == 0) begin #400; SCLK = 1; #180; SCLK = 0; #420; end else #1000;
        for (int n = 0; n < nb; n++) begin
            // the host's rising edge: sample MISO
            rx[n / 8][7 - n % 8] = miso_pad;
            if (fk == 2 && fp == n) begin SCLK = 1; #170; SCLK = 0; #160; SCLK = 1; #170; end
            else if (fk == 0 && fp == n) begin #500; end
            else if (fk == 3 && fp + 1 == n) begin #500; end           // already high from pulse fp
            else begin SCLK = 1; #500; end
            // the host's falling edge: next MOSI bit
            if (!(fk == 3 && fp == n)) SCLK = 0;
            MOSI = (n + 1 < nb) ? tx[(n + 1) / 8][7 - (n + 1) % 8] : 1'b0;
            if (n + 1 < nb) begin
                if (fk == 1 && fp == n + 1) begin #160; SCLK = 1; #180; SCLK = 0; #160; end
                else #500;
            end
        end
        SCLK = 1'b0;
        #300; CS_N = 1'b1; #(tidle);
    endtask

    integer n_ferr, n_pop, n_snap;
    always @(negedge CS_N) begin n_ferr = 0; n_pop = 0; n_snap = 0; end
    always @(posedge MCLK) begin
        if (dut.frame_err) n_ferr++;
        if (dut.u_fifo.pop_ok) n_pop++;
        if (dut.smp_snap) n_snap++;
    end

    task automatic wr(input logic [6:0] a, input logic [7:0] d);
        tx[0] = {1'b0, a}; tx[1] = d; tx[2] = crc8u(crc8u(8'h00, tx[0]), d);
        xfer(dut.crc_en ? 3 : 2, -1, 0, 2000.0);
    endtask
    task automatic rd(input logic [6:0] a, output logic [7:0] v, output bit ok);
        tx[0] = {1'b1, a}; tx[1] = 0; tx[2] = 0;
        xfer(3, -1, 0, 2000.0);
        v = rx[1]; ok = (rx[2] == crc8u(crc8u(8'h00, tx[0]), rx[1])) && rx[0][7:6] == 2'b10;
    endtask


    integer n_edges = 0;
    always @(DRDY_N) n_edges++;
    initial begin
        logic [7:0] v, c; bit ok;
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        wr(7'h55, 8'h03);                                   // CRC on, pulse mode
        wr(7'h09, 8'h00);                                   // ALERT_MASK_D 0 (step 3)
        wr(7'h52, 8'd29);
        wr(7'h10, 8'h11);                                   // START
        wait (dut.seq_state == ST_RUN);
        rd(7'h06, v, ok); wr(7'h06, v);
        repeat (2 * 32768) @(posedge MCLK);
        // a normal sample read
        tx[0] = SMP_HDR; for (int b = 1; b < 8; b++) tx[b] = 0; xfer(8, -1, 0, 2000.0);
        c = crc8u(8'h00, SMP_HDR); for (int b = 1; b < 7; b++) c = crc8u(c, rx[b]);
        $display("before: header 0x%02h, word %02h %02h%02h %02h%02h%02h crc_ok %0d", rx[0], rx[1], rx[2], rx[3], rx[4], rx[5], rx[6], c == rx[7]);
        // the unexpected reset
        RESET_N = 1'b0; #1000; RESET_N = 1'b1; #2000;
        tx[0] = SMP_HDR; for (int b = 1; b < 8; b++) tx[b] = 0; xfer(8, -1, 0, 2000.0);
        c = crc8u(8'h00, SMP_HDR); for (int b = 1; b < 7; b++) c = crc8u(c, rx[b]);
        $display("after:  sample read: header 0x%02h (ALERT %0d DATA %0d), word %02h %02h%02h %02h%02h%02h crc_ok %0d",
                 rx[0], rx[0][STATUS_ALERT_LSB], rx[0][STATUS_DATA_LSB], rx[1], rx[2], rx[3], rx[4], rx[5], rx[6], c == rx[7]);
        rd(7'h05, v, ok); $display("after:  FIFO_LEVEL CRC read: %02h %02h %02h crc_ok %0d", rx[0], rx[1], rx[2], ok);
        rd(7'h05, v, ok); $display("after:  FIFO_LEVEL CRC read again: crc_ok %0d", ok);
        rd(7'h06, v, ok); $display("after:  ERR CRC read: %02h %02h %02h crc_ok %0d", rx[0], rx[1], rx[2], ok);
        rd(7'h03, v, ok); $display("after:  STATUS CRC read: %02h %02h %02h crc_ok %0d", rx[0], rx[1], rx[2], ok);
        tx[0] = 8'h06; tx[1] = 8'h02; tx[2] = crc8u(crc8u(8'h00, 8'h06), 8'h02); xfer(3, -1, 0, 2000.0);
        $display("after:  CRC write of ERR: MISO %02h %02h %02h (rule (a) %0d), ERR now %02h", rx[0], rx[1], rx[2],
                 rx[0][7:6] == 2'b10 && rx[1] == 0 && rx[2] == 0, dut.u_regs.err);
        tx[0] = 8'h10; tx[1] = 8'h44; tx[2] = crc8u(crc8u(8'h00, 8'h10), 8'h44); xfer(3, -1, 0, 2000.0);
        $display("after:  CRC command APPLY_NR: MISO %02h %02h %02h (rule (a) %0d), pending %0d", rx[0], rx[1], rx[2],
                 rx[0][7:6] == 2'b10 && rx[1] == 0 && rx[2] == 0, dut.u_regs.pend);
        tx[0] = 8'hD5; tx[1] = 0; tx[2] = 0; xfer(3, -1, 0, 2000.0);
        $display("after:  mode probe: %02h %02h %02h", rx[0], rx[1], rx[2]);
        n_edges = 0; repeat (3 * 32768) @(posedge MCLK);
        $display("after:  DRDY_N edges in the next 3 ms: %0d (DRDY_N %b, IF_CFG %02h)", n_edges, DRDY_N, {dut.u_regs.r_drdy, dut.u_regs.r_crc});
        $finish;
    end
endmodule
`default_nettype wire
