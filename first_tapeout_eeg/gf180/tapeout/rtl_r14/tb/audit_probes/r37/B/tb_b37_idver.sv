// audit round 37, auditor B: step 3's CRC reads of ID (0x80) and VERSION (0x81) in step 3's state (IDLE, FIFO empty,
// CRC on), and of VERSION while a sample is at the FIFO's head (RUN): every single fault as the host and the chip see
// it apart - one header bit flipped on MOSI; one SCLK fault at the chip's pin: a missed pulse, an extra pulse in the low
// phase before pulse k, a bounce inside pulse k's high phase, pulses k and k+1 merged. The host samples MISO at its
// own rising edges and accepts a read when rule (a) holds (first byte 10xxxxxx) and the CRC of (header, data) matches.
`timescale 1ns / 1ps
`default_nettype none
module tb_b37_idver;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    logic SCLK_CHIP = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG;
    wire [3:0] CPF_TRIM, OFEN;
    wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.MCLK(MCLK), .RESET_N(RESET_N), .SCLK(SCLK_CHIP),
        .CS_N(CS_N), .MOSI(MOSI), .MISO(MISO), .MISO_OE(MISO_OE), .DRDY_N(DRDY_N), .RAW_DATA(RAW_DATA),
        .RAW_CLK(RAW_CLK), .ADC_RST_N(ADC_RST_N), .TH_CAPTURE(TH_CAPTURE), .DAC_LOAD(DAC_LOAD), .DWA_EN(DWA_EN),
        .CODE(CODE), .CMP_STROBE(CMP_STROBE), .DAC_CLK(DAC_CLK), .CHOP(CHOP), .CHOP_OUT(CHOP_OUT),
        .CHOP_BLANK(CHOP_BLANK), .AFE_RST(AFE_RST), .CHOP_EN(CHOP_EN), .TEST_CFG(TEST_CFG), .CPF_TRIM(CPF_TRIM),
        .AFE_IBIAS(AFE_IBIAS), .BTRIM_P(BTRIM_P), .BTRIM_N(BTRIM_N), .OFM(OFM), .OFS(OFS), .OFEN(OFEN), .CHOP1(CHOP1));
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    wire #(15.0) miso_pin = MISO;
    wire #(15.0) oe_pin = MISO_OE;
    wire miso_pad = oe_pin ? miso_pin : 1'b1;          // pulled up (PIN-04)

    function automatic logic [7:0] crc2(input logic [7:0] a, input logic [7:0] b);
        logic [7:0] c; c = a;
        for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        c = c ^ b;
        for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        return c;
    endfunction

    logic [7:0] tx [0:15];
    logic [7:0] rx [0:15];
    // fault: 0 none, 1 MOSI flip of header bit fk, 2 missed pulse fk, 3 extra pulse before pulse fk, 4 bounce in pulse
    // fk, 5 pulses fk and fk+1 merged
    task automatic xfer(input integer nbytes, input integer fault, input integer fk);
        integer total;
        logic b;
        total = 8 * nbytes;
        CS_N = 1'b0;
        b = tx[0][7]; if (fault == 1 && fk == 0) b = ~b; MOSI = b;
        if (fault == 3 && fk == 0) begin
            #(250.0); SCLK_CHIP = 1'b1; #(120.0); SCLK_CHIP = 1'b0; #(230.0);
        end else #(600.0);
        for (int n = 0; n < total; n++) begin
            // rising edge of the host's pulse n
            if (!(fault == 2 && fk == n) && !(fault == 5 && fk + 1 == n)) SCLK_CHIP = 1'b1;
            rx[n / 8][7 - (n % 8)] = miso_pad;
            if (fault == 4 && fk == n) begin
                #(120.0); SCLK_CHIP = 1'b0; #(120.0); SCLK_CHIP = 1'b1; #(260.0);
            end else #(500.0);
            if (!(fault == 5 && fk == n)) SCLK_CHIP = 1'b0;
            b = (n + 1 < total) ? tx[(n + 1) / 8][7 - ((n + 1) % 8)] : 1'b0;
            if (fault == 1 && fk == n + 1 && n + 1 < 8) b = ~b;
            MOSI = b;
            if (n + 1 < total) begin
                if (fault == 3 && fk == n + 1) begin
                    #(190.0); SCLK_CHIP = 1'b1; #(120.0); SCLK_CHIP = 1'b0; #(190.0);
                end else #(500.0);
            end
        end
        SCLK_CHIP = 1'b0;
        #(300.0); CS_N = 1'b1; #(1500.0);
    endtask
    task automatic wr(input logic [6:0] a, input logic [7:0] v, input bit crc);
        tx[0] = {1'b0, a}; tx[1] = v; tx[2] = crc2(tx[0], v);
        xfer(crc ? 3 : 2, 0, 0);
    endtask
    task automatic rd(input logic [6:0] a, output logic [7:0] v);
        tx[0] = {1'b1, a}; tx[1] = 8'h00; tx[2] = 8'h00;
        xfer(3, 0, 0);
        v = rx[1];
    endtask

    integer n_trials = 0, n_acc = 0, n_wrong = 0, n_rej = 0, n_snap = 0, tot_snap = 0;
    always @(posedge MCLK) if (dut.smp_snap) n_snap = n_snap + 1;
    task automatic setup(input integer alert, input integer run);
        logic [7:0] v;
        RESET_N = 1'b0; #(300.0); RESET_N = 1'b1; #(2000.0);
        wr(7'h55, 8'h01, 1'b0);                 // step 3: CRC on
        if (!alert) wr(7'h06, 8'h01, 1'b1);     // step 2/3: RESET_FLAG cleared (ALERT 0)
        if (run) begin
            wr(7'h50, 8'h05, 1'b1);
            wr(7'h10, CMD_START, 1'b1);
            #(9.5e6);                           // RUN (T_WARM 5 ms + T_REC + ALIGN + FILL), samples stored
        end
    endtask
    task automatic trial(input logic [7:0] h, input logic [7:0] truth, input integer fault, input integer fk,
                         input integer alert, input integer run);
        logic ok;
        if (!alert) wr(7'h06, 8'hFF, 1'b1);   // ERR cleared: ALERT 0 at the header
        n_snap = 0;
        tx[0] = h; tx[1] = 8'h00; tx[2] = 8'h00;
        xfer(3, fault, fk);
        ok = (rx[0][7:6] == 2'b10) && (rx[2] == crc2(h, rx[1]));
        n_trials++;
        tot_snap = tot_snap + n_snap;
        if (!ok) n_rej++;
        else begin
            n_acc++; $display("ACC h=%02h fault=%0d k=%0d alert=%0d run=%0d MISO %02h %02h %02h snap=%0d", h, fault, fk, alert, run, rx[0], rx[1], rx[2], n_snap);
            if (rx[1] !== truth) begin
                n_wrong++;
                $display("WRONG ACCEPTED h=%02h fault=%0d k=%0d alert=%0d run=%0d: MISO %02h %02h %02h (true 0x%02h)",
                         h, fault, fk, alert, run, rx[0], rx[1], rx[2], truth);
            end
        end
    endtask
    initial begin
        #(300.0);
        for (int run = 0; run < 2; run++)
          for (int alert = 0; alert < 2; alert++) begin
            setup(alert, run);
            for (int r = 0; r < 2; r++) begin
                logic [7:0] h, truth;
                h = r ? 8'h81 : 8'h80; truth = r ? VERSION_VERSION_RST : ID_ID_RST;
                if (run && !r) continue;                   // RUN: VERSION only
                trial(h, truth, 0, 0, alert, run);
                for (int k = 0; k < 8; k++)  trial(h, truth, 1, k, alert, run);
                for (int k = 0; k < 24; k++) trial(h, truth, 2, k, alert, run);
                for (int k = 0; k < 24; k++) trial(h, truth, 3, k, alert, run);
                for (int k = 0; k < 24; k++) trial(h, truth, 4, k, alert, run);
                for (int k = 0; k < 23; k++) trial(h, truth, 5, k, alert, run);
            end
          end
        $display("trials %0d: rejected %0d, accepted %0d, accepted with a wrong value %0d; window copies (snap) %0d", n_trials, n_rej, n_acc, n_wrong, tot_snap);
        $finish;
    end
endmodule
`default_nettype wire
