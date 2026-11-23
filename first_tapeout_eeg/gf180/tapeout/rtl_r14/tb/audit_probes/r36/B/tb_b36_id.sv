// audit round 36, auditor B: every single fault of the host procedure's CRC-off frames as the chip sees them
// (one MOSI bit flipped, one SCLK rise missed or merged = a MOSI bit skipped, one extra rise or bounce = a MOSI bit
// read twice), each from RESET_N, then the whole map read back: which registers change, and to what.
`timescale 1ns / 1ps
`default_nettype none
module tb_b36_id;
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

    wire miso_pad = MISO_OE ? MISO : 1'b1;          // pulled up
    logic [7:0] rx [0:127];
    logic       bits [0:255];
    integer     nb;
    // nbits rising edges, MOSI from bits[]; MISO sampled at each rise
    task automatic xfer(input integer nbits);
        CS_N = 1'b0; MOSI = bits[0];
        #(400.0);
        for (int n = 0; n < nbits; n++) begin
            MOSI = bits[n]; #(150.0);
            SCLK = 1'b1;
            rx[n / 8][7 - (n % 8)] = miso_pad;
            #(250.0);
            SCLK = 1'b0;
            #(100.0);
        end
        #(200.0); CS_N = 1'b1; #(1500.0);
    endtask
    task automatic load_bytes(input logic [7:0] b0, input logic [7:0] b1, input logic [7:0] b2, input integer n);
        logic [7:0] bb [0:2];
        bb[0] = b0; bb[1] = b1; bb[2] = b2;
        nb = 8 * n;
        for (int i = 0; i < nb; i++) bits[i] = bb[i / 8][7 - (i % 8)];
    endtask
    function automatic logic [7:0] crc2(input logic [7:0] a, input logic [7:0] b);
        logic [7:0] c; c = a;
        for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        c = c ^ b;
        for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        return c;
    endfunction
    // the map as the host reads it: mode probe first (fault free), then CRC off one burst, CRC on one read each
    logic [7:0] map [0:127];
    bit crc_mode;
    task automatic read_map();
        logic [7:0] h;
        load_bytes(8'hD5, 8'h00, 8'h00, 3); xfer(24);
        crc_mode = rx[1][0] && (rx[2] == crc2(8'hD5, rx[1]));
        if (!crc_mode && !(rx[1][0] == 1'b0 && rx[2] == 8'h00)) $display("PROBE neither: %02h %02h %02h", rx[0], rx[1], rx[2]);
        if (!crc_mode) begin
            nb = 8 * 116;
            for (int i = 0; i < nb; i++) bits[i] = (i == 0);
            xfer(nb);
            for (int a = 0; a < 115; a++) map[a] = rx[a + 1];
        end else begin
            for (int a = 0; a < 115; a++) begin
                h = 8'h80 | a[6:0];
                load_bytes(h, 8'h00, 8'h00, 3); xfer(24);
                map[a] = rx[1];
                if (rx[2] !== crc2(h, rx[1])) $display("CRC read 0x%02h bad", a);
            end
        end
    endtask
    logic [7:0] ref_map [0:127];
    integer ntr = 0;
    string  kinds [0:2] = '{"flip", "skip", "dup"};
    task automatic trial(input logic [7:0] b0, input logic [7:0] b1, input logic [7:0] b2, input integer n,
                         input integer kind, input integer pos, input string tag);
        logic orig [0:255];
        integer m;
        RESET_N = 1'b0; #(200.0); RESET_N = 1'b1; #(1500.0);
        load_bytes(b0, b1, b2, n);
        for (int i = 0; i < nb; i++) orig[i] = bits[i];
        m = nb;
        if (kind == 0) bits[pos] = ~orig[pos];
        else if (kind == 1) begin for (int i = pos; i < nb - 1; i++) bits[i] = orig[i + 1]; m = nb - 1; end
        else if (kind == 2) begin for (int i = nb; i > pos; i--) bits[i] = orig[i - 1]; m = nb + 1; end
        xfer(m);
        read_map();
        for (int a = 0; a < 115; a++)
            if (a != 3 && a != 6 && map[a] !== ref_map[a])
                $display("CHANGE %s %s@%0d: 0x%02h = 0x%02h (reset 0x%02h)%s", tag, kinds[kind], pos, a, map[a], ref_map[a],
                         crc_mode ? " [CRC on]" : "");
        if (crc_mode) $display("CRCON %s %s@%0d", tag, kinds[kind], pos);
        ntr++;
    endtask
    initial begin
        #(300.0); RESET_N = 1'b1; #(1500.0);
        load_bytes(8'h80, 8'h00, 8'h00, 3); xfer(24);
        $display("step 2 ID read [80 00 00], CRC off: MISO %02h %02h %02h", rx[0], rx[1], rx[2]);
        load_bytes(8'hC0, 8'h00, 8'h00, 3); xfer(24);
        $display("same read, MOSI bit 6 flipped [C0 00 00]: MISO %02h %02h %02h", rx[0], rx[1], rx[2]);
        load_bytes(8'h86, 8'h00, 8'h00, 3); xfer(24);
        $display("ERR read after it [86 00 00]: MISO %02h %02h %02h (ERR, DFLAG)", rx[0], rx[1], rx[2]);
        $finish;
    end
endmodule
`default_nettype wire
