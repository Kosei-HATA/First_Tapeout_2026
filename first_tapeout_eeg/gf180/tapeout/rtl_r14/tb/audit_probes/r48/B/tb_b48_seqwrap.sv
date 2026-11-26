// tb_b48_seqwrap - audit round 48, auditor B probe (not a repository bench): SEQ counts every output time and wraps
// at 65,536 (DAT-03); START and STOP do not change it. After a STOP and an idle time of k x 65.536 s the first sample
// after START carries the SEQ of the last word used before the STOP. The 65.536 s are emulated by depositing
// dut.seq_cnt in FILL (as tb_top_r14's K deposits 0xFFFE), after which the counter runs on by itself.
`timescale 1ns / 1ps
`default_nettype none
module tb_b48_seqwrap;
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
    wire miso_pad = oe_pin ? miso_pin : 1'b1;
    function automatic logic [7:0] crc8u(input logic [7:0] c0, input logic [7:0] d);
        logic [7:0] c; c = c0 ^ d;
        for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        return c;
    endfunction
    logic [7:0] tx [0:15], rx [0:15];
    task automatic xfer(input integer nbits);
        CS_N = 1'b0; MOSI = tx[0][7]; #1000;
        for (int n = 0; n < nbits; n++) begin
            rx[n / 8][7 - n % 8] = miso_pad;
            SCLK = 1; #500; SCLK = 0;
            MOSI = (n + 1 < nbits) ? tx[(n + 1) / 8][7 - (n + 1) % 8] : 1'b0;
            if (n + 1 < nbits) #500;
        end
        #300; CS_N = 1'b1; #2000;
    endtask
    task automatic wr(input logic [6:0] a, input logic [7:0] d);
        tx[0] = {1'b0, a}; tx[1] = d; tx[2] = crc8u(crc8u(8'h00, tx[0]), d);
        xfer(dut.crc_en ? 24 : 16);
    endtask
    logic [7:0] last [0:5];
    task automatic smp(input string tag, output logic [15:0] seq, output bit valid);
        logic [7:0] c;
        tx[0] = SMP_HDR; for (int b = 1; b < 8; b++) tx[b] = 0; xfer(64);
        c = crc8u(8'h00, SMP_HDR); for (int b = 1; b < 7; b++) c = crc8u(c, rx[b]);
        seq = {rx[2], rx[3]}; valid = rx[1][SMP_VALID_LSB];
        $display("%s: header 0x%02h ALERT %0d, word %02h %02h%02h %02h%02h%02h, CRC ok %0d", tag, rx[0],
                 rx[0][STATUS_ALERT_LSB], rx[1], rx[2], rx[3], rx[4], rx[5], rx[6], c == rx[7]);
    endtask
    initial begin
        logic [15:0] s, s2; bit v;
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        wr(7'h55, 8'h01); wr(7'h09, 8'h00); wr(7'h10, 8'h11);                 // CRC on, ALERT_MASK_D 0, START
        wait (dut.seq_state == ST_RUN);
        tx[0] = 8'h86; tx[1] = 0; tx[2] = 0; xfer(24); wr(7'h06, rx[1]);      // clear ERR (RESET_FLAG)
        repeat (2 * 32768) @(posedge MCLK);
        do smp("read before STOP", s, v); while (!(v && dut.fifo_level == 0));
        $display("last word used before STOP: SEQ 0x%04h", s);
        wr(7'h10, 8'h22);                                                      // STOP
        repeat (3 * 32768) @(posedge MCLK);                                    // idle (k x 65.536 s emulated below)
        wr(7'h10, 8'h11);                                                      // START
        wait (dut.seq_state == ST_FILL);
        @(negedge MCLK); dut.seq_cnt = s - 16'd2;                              // = 65,536 x k outputs later
        wait (dut.seq_state == ST_RUN);
        repeat (100) @(posedge MCLK);
        smp("first read after START", s2, v);
        $display("first word after START: VALID %0d, SEQ 0x%04h (last used 0x%04h): %s", v, s2, s,
                 (s2 == s) ? "same SEQ, different bytes" : "SEQ differs");
        $finish;
    end
endmodule
`default_nettype wire
