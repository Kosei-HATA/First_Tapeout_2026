// audit round 44, B: every readable register (and active copy) read with CRC under every single fault (one header bit
// flipped on MOSI; one SCLK fault at the chip's pin: missed pulse k, extra pulse before pulse k, bounce in pulse k,
// pulses k and k+1 merged), with random legal contents, in IDLE (FIFO empty) and in RUN (samples in the FIFO).
// The host accepts a read when rule (a) holds and the CRC of (header, data) matches. Every accepted read is logged with
// the true value and the header the chip decoded; tb_b44_slipall.py compares them with regmap.slip_hazards.
// (fault-injecting xfer as in audit_probes/r37/B/tb_b37_idver.sv)
`timescale 1ns / 1ps
`default_nettype none
module tb_b44_slipall;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    logic SCLK_CHIP = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
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
    task automatic xfer(input integer nbytes, input integer fault, input integer fk);
        integer total; logic b;
        total = 8 * nbytes;
        CS_N = 1'b0;
        b = tx[0][7]; if (fault == 1 && fk == 0) b = ~b; MOSI = b;
        if (fault == 3 && fk == 0) begin #(250.0); SCLK_CHIP = 1'b1; #(120.0); SCLK_CHIP = 1'b0; #(230.0); end
        else #(600.0);
        for (int n = 0; n < total; n++) begin
            if (!(fault == 2 && fk == n) && !(fault == 5 && fk + 1 == n)) SCLK_CHIP = 1'b1;
            rx[n / 8][7 - (n % 8)] = miso_pad;
            if (fault == 4 && fk == n) begin #(120.0); SCLK_CHIP = 1'b0; #(120.0); SCLK_CHIP = 1'b1; #(260.0); end
            else #(500.0);
            if (!(fault == 5 && fk == n)) SCLK_CHIP = 1'b0;
            b = (n + 1 < total) ? tx[(n + 1) / 8][7 - ((n + 1) % 8)] : 1'b0;
            if (fault == 1 && fk == n + 1 && n + 1 < 8) b = ~b;
            MOSI = b;
            if (n + 1 < total) begin
                if (fault == 3 && fk == n + 1) begin #(190.0); SCLK_CHIP = 1'b1; #(120.0); SCLK_CHIP = 1'b0; #(190.0); end
                else #(500.0);
            end
        end
        SCLK_CHIP = 1'b0; #(300.0); CS_N = 1'b1; #(1500.0);
    endtask
    task automatic wr(input logic [6:0] a, input logic [7:0] v, input bit crc);
        tx[0] = {1'b0, a}; tx[1] = v; tx[2] = crc2(tx[0], v); xfer(crc ? 3 : 2, 0, 0);
    endtask
    task automatic rd(input logic [6:0] a, output logic [7:0] v);
        tx[0] = {1'b1, a}; tx[1] = 8'h00; tx[2] = 8'h00; xfer(3, 0, 0); v = rx[1];
    endtask
    // capture: the header the chip decoded and the data byte it loaded after it
    logic [7:0] dec_hdr, dec_txd; logic dec_seen;
    always @(negedge MCLK) begin
        if (dut.u_spi.cs_start) dec_seen = 1'b0;
        if (dut.u_spi.sclk_rise && dut.u_spi.st == 4'd1 && dut.u_spi.bit_cnt == 3'd7) dec_hdr = dut.u_spi.rx_byte;
        if (dut.u_spi.sclk_fall && dut.u_spi.bit_cnt == 3'd0 && !dec_seen && dut.u_spi.st != 4'd1) begin
            dec_txd = dut.u_spi.tx_next; dec_seen = 1'b1;
        end
    end
    integer fd, n_trials = 0, n_acc = 0, n_wrong = 0;
    logic [6:0] addrs [0:63];
    integer na;
    task automatic trial(input logic [6:0] a, input integer fault, input integer fk, input integer ctx);
        logic [7:0] h, truth, v;
        h = {1'b1, a};
        wr(7'h06, 8'hFF, 1'b1);                       // ERR cleared: ALERT 0 at the header (unless a mask is off)
        rd(a, truth);                                 // the clean value just before
        dec_hdr = 8'hxx; dec_seen = 1'b0;
        tx[0] = h; tx[1] = 8'h00; tx[2] = 8'h00;
        xfer(3, fault, fk);
        n_trials++;
        if ((rx[0][7:6] == 2'b10) && (rx[2] == crc2(h, rx[1]))) begin
            n_acc++;
            if (dec_hdr == h && dec_seen) truth = dec_txd;   // the value the chip sent for this header
            if (rx[1] !== truth) n_wrong++;
            $fdisplay(fd, "ACC ctx=%0d a=%02h fault=%0d k=%0d st=%02h read=%02h true=%02h dec=%02h", ctx, a, fault, fk,
                      rx[0], rx[1], truth, dec_hdr);
        end
    endtask
    task automatic randomize_regs(input integer run);
        logic [7:0] v;
        begin
            integer r, m, mx;
            r = $urandom_range(0, 4);
            mx = (r == 1) ? 127 : (r == 2) ? 255 : (r == 3) ? 511 : 1023;
            m = $urandom_range(0, mx);
            wr(7'h22, {3'b000, 1'($urandom_range(0, 1)), 1'b0, 3'(r)}, 1'b1);
            wr(7'h20, 8'(m >> 8), 1'b1);
            wr(7'h21, 8'(m & 255), 1'b1);
        end
        wr(7'h23, $urandom_range(0, 3), 1'b1);
        wr(7'h24, $urandom_range(0, 15), 1'b1);
        wr(7'h25, {2'b00, 2'($urandom_range(0, 3)), 2'b00, 2'($urandom_range(0, 3))}, 1'b1);
        wr(7'h26, 8'h01, 1'b1);                       // 128 kHz
        wr(7'h27, {3'b000, 1'($urandom_range(0, 1)), 1'b0, 3'($urandom_range(0, 5))}, 1'b1);
        wr(7'h28, $urandom_range(1, 15), 1'b1);
        wr(7'h08, $urandom_range(0, 255) | 8'h02, 1'b1);   // FRAME_ERR kept in the mask (step 6)
        wr(7'h09, $urandom_range(0, 3), 1'b1);
        wr(7'h50, run ? 8'd5 : $urandom_range(5, 255), 1'b1);
        wr(7'h51, run ? 8'd0 : $urandom_range(0, 255), 1'b1);
        wr(7'h52, run ? 8'd29 : $urandom_range(29, 255), 1'b1);
        wr(7'h53, $urandom_range(3, 255), 1'b1);
        wr(7'h54, $urandom_range(13, 255), 1'b1);
        wr(7'h55, {6'd0, 1'($urandom_range(0, 1)), 1'b1}, 1'b1);
        wr(7'h11, 8'h3C, 1'b1);
        wr(7'h60, $urandom_range(0, 31), 1'b1);
        wr(7'h61, run ? 8'h00 : $urandom_range(0, 3), 1'b1);
        wr(7'h62, {5'd0, 2'($urandom_range(0, 3)), 1'b0}, 1'b1);
        wr(7'h11, 8'h00, 1'b1);
        if (!run) wr(7'h10, CMD_APPLY, 1'b1);        // IDLE: the copies take the random values
        #(40000.0);
        wr(7'h06, 8'hFF, 1'b1);
    endtask
    initial begin
        integer ctx;
        logic [7:0] v;
        if (!$value$plusargs("seed=%d", ctx)) ctx = 1;
        void'($urandom(ctx));
        fd = $fopen(ctx == 44 ? "slipall.txt" : "slipall2.txt", "w");
        na = 0;
        for (int a = 0; a <= 12; a++) begin addrs[na] = a; na++; end
        for (int a = 32; a <= 40; a++) begin addrs[na] = a; na++; end
        for (int a = 48; a <= 56; a++) begin addrs[na] = a; na++; end
        for (int a = 80; a <= 85; a++) begin addrs[na] = a; na++; end
        addrs[na] = 7'h60; na++; addrs[na] = 7'h61; na++; addrs[na] = 7'h62; na++;
        addrs[na] = 7'h70; na++; addrs[na] = 7'h71; na++;
        #(300.0); RESET_N = 1'b1; #(2000.0);
        wr(7'h55, 8'h01, 1'b0);                       // CRC on
        for (int c = 0; c < 2; c++) begin
            integer run; run = c % 2;
            if (run) begin
                if (dut.seq_state != 4'd0) begin wr(7'h10, CMD_STOP, 1'b1); #(40000.0); end
                randomize_regs(1);
                wr(7'h10, CMD_START, 1'b1);
                #(12.0e6);                            // RUN with samples
            end else begin
                if (dut.seq_state != 4'd0) begin wr(7'h10, CMD_STOP, 1'b1); #(40000.0); end
                rd(7'h05, v);
                while (v != 0) begin tx[0] = SMP_HDR; for (int i = 1; i < 8; i++) tx[i] = 0; xfer(8, 0, 0); rd(7'h05, v); end
                randomize_regs(0);
            end
            $display("context %0d (run %0d): state %0d, FIFO %0d", c, run, dut.seq_state, dut.fifo_level);
            for (int i = 0; i < na; i++) begin
                for (int k = 0; k < 8; k++)  trial(addrs[i], 1, k, c);
                for (int k = 0; k < 24; k++) trial(addrs[i], 2, k, c);
                for (int k = 0; k < 24; k++) trial(addrs[i], 3, k, c);
                for (int k = 0; k < 24; k++) trial(addrs[i], 4, k, c);
                for (int k = 0; k < 23; k++) trial(addrs[i], 5, k, c);
                // keep the FIFO from filling in RUN (read one sample now and then)
                if (run && (i % 3 == 2)) begin tx[0] = SMP_HDR; for (int j = 1; j < 8; j++) tx[j] = 0; xfer(8, 0, 0); end
            end
        end
        $fclose(fd);
        $display("tb_b44_slipall: %0d faulted reads, %0d accepted, %0d accepted with a value other than the true one", n_trials, n_acc, n_wrong);
        $finish;
    end
endmodule
`default_nettype wire
