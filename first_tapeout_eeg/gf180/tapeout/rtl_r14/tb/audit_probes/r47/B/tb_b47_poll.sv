// tb_b47_poll - audit round 47, auditor B probe: header-only CRC-on reads of all 128 addresses in RUN (rule (b)'s
// status poll); derived from tb_b47_sclk (not part of the repository's benches).
// The four single SCLK faults of the slip model (regmap.slip_hazards: a missed pulse, an extra pulse in the low phase
// before pulse k, a bounce inside pulse k's high phase, pulses k and k+1 merged) at every pulse of an 8-byte CRC-on
// sample read in RUN, at 1 MHz. Requirements 5.4 step 6 relies on: the chip raises FRAME_ERR and does not pop in every
// such frame, the very next header (CS_N high 4 MCLK) shows ALERT 0 -> 1, and the host's slipped copy passes the
// sample CRC only rarely (step 6 quotes about 0.26 %).
`timescale 1ns / 1ps
`default_nettype none
module tb_b47_poll;
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


    initial begin
        logic [7:0] v; bit ok; integer n_clean = 0, n_addr = 0, n_frame = 0, n_other = 0;
        string s_addr = "", s_frame = "";
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        wr(7'h55, 8'h01); wr(7'h09, 8'h00); wr(7'h52, 8'd29); wr(7'h10, 8'h11);
        wait (dut.seq_state == ST_RUN);
        rd(7'h06, v, ok); wr(7'h06, v);
        for (int a = 0; a < 128; a++) begin
            tx[0] = 8'h80 | a[7:0]; xfer(1, -1, 0, 2000.0);
            if (dut.u_regs.err == 8'h00) n_clean++;
            else if (dut.u_regs.err == 8'h08) begin n_addr++; end
            else if (dut.u_regs.err == 8'h02) begin n_frame++; s_frame = {s_frame, $sformatf(" %02h", a)}; end
            else n_other++;
            if (dut.u_regs.err != 8'h00) begin rd(7'h06, v, ok); wr(7'h06, v); end
        end
        $display("header-only CRC reads in RUN: %0d clean, %0d ADDR_ERR, %0d FRAME_ERR (addresses%s), %0d other",
                 n_clean, n_addr, n_frame, s_frame, n_other);
        $finish;
    end
endmodule
`default_nettype wire
