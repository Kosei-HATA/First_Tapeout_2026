// tb_b48_seu_pop - audit round 48, auditor B probe (derived from audit_probes/r47/B/tb_b47_seu.sv; not a repository
// bench). A one-bit upset of eeg_spi_slave's st between legal codes that ADDS a pop: RREG 0010 -> SDONE 0110 (bit 2)
// in a register read, after a sample read that copied the head and ended without a pop (the host's own re-read with
// 8 extra SCLKs, requirements 5.4 step 6), so the FIFO's `held` is still 1.
`timescale 1ns / 1ps
`default_nettype none
module tb_b48_seu_pop;
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
    integer upset_to = -1;
    task automatic xfer(input integer nbits);              // 1 MHz, 500/500 ns
        CS_N = 1'b0; MOSI = tx[0][7]; #1000;
        for (int n = 0; n < nbits; n++) begin
            rx[n / 8][7 - n % 8] = miso_pad;
            SCLK = 1; #500; SCLK = 0;
            MOSI = (n + 1 < nbits) ? tx[(n + 1) / 8][7 - (n + 1) % 8] : 1'b0;
            if (n + 1 < nbits) #500;
        end
        #150; if (upset_to >= 0) begin @(negedge MCLK); $display("  upset: st %0d -> %0d", dut.u_spi.st, upset_to); dut.u_spi.st = upset_to[3:0]; end
        #150; CS_N = 1'b1; #2000;
    endtask
    integer n_ferr, n_pop, n_preq;
    always @(negedge CS_N) begin n_ferr = 0; n_pop = 0; n_preq = 0; end
    always @(posedge MCLK) begin
        if (dut.frame_err) n_ferr++;
        if (dut.u_fifo.pop_ok) n_pop++;
        if (dut.smp_pop) n_preq++;
    end
    task automatic wr(input logic [6:0] a, input logic [7:0] d);
        tx[0] = {1'b0, a}; tx[1] = d; tx[2] = crc8u(crc8u(8'h00, tx[0]), d);
        xfer(dut.crc_en ? 24 : 16);
    endtask
    task automatic smp(input integer nbits, input string tag);
        logic [7:0] c;
        tx[0] = SMP_HDR; for (int b = 1; b < 9; b++) tx[b] = 0; xfer(nbits);
        c = crc8u(8'h00, SMP_HDR); for (int b = 1; b < 7; b++) c = crc8u(c, rx[b]);
        $display("%s: %0d bits, header 0x%02h ALERT %0d, SEQ %02h%02h, crc_ok %0d, pop requests %0d, pops %0d, FRAME_ERR %0d, held %0d, level %0d",
                 tag, nbits, rx[0], rx[0][STATUS_ALERT_LSB], rx[2], rx[3], c == rx[7], n_preq, n_pop, n_ferr,
                 dut.u_fifo.held, dut.fifo_level);
    endtask

    initial begin
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        wr(7'h55, 8'h01); wr(7'h09, 8'h00); wr(7'h52, 8'd29); wr(7'h10, 8'h11);
        wait (dut.seq_state == ST_RUN);
        tx[0] = 8'h86; tx[1] = 0; tx[2] = 0; xfer(24); wr(7'h06, rx[1]);          // clear ERR
        repeat (4 * 32768) @(posedge MCLK);
        smp(64, "read A (normal)");
        smp(72, "read B (CRC taken as bad: 8 extra SCLKs)");
        wr(7'h06, 8'h02);                                                        // step 6: clear the FRAME_ERR
        $display("after the FRAME_ERR clear: ERR 0x%02h, held %0d, level %0d", dut.u_regs.err, dut.u_fifo.held,
                 dut.fifo_level);
        upset_to = 6;                                       // FIFO_LEVEL read: RREG -> SDONE just before CS_N rises
        tx[0] = 8'h85; tx[1] = 0; tx[2] = 0; xfer(24);
        upset_to = -1;
        $display("FIFO_LEVEL CRC read with the upset: MISO %02h %02h %02h (CRC ok %0d), pop requests %0d, pops %0d, FRAME_ERR %0d, level %0d, ERR 0x%02h",
                 rx[0], rx[1], rx[2], rx[2] == crc8u(crc8u(8'h00, 8'h85), rx[1]), n_preq, n_pop, n_ferr,
                 dut.fifo_level, dut.u_regs.err);
        smp(64, "read C (the re-read)");
        smp(72, "read E (CRC taken as bad: 8 extra SCLKs)");
        wr(7'h06, 8'h02);
        upset_to = 6;                                       // header-only STATUS poll (0x83): RREG -> SDONE
        tx[0] = 8'h83; xfer(8);
        upset_to = -1;
        $display("header-only poll 0x83 with the upset: MISO %02h, pop requests %0d, pops %0d, FRAME_ERR %0d, level %0d",
                 rx[0], n_preq, n_pop, n_ferr, dut.fifo_level);
        smp(64, "read F (the re-read)");
        repeat (2 * 32768) @(posedge MCLK);
        smp(8, "read G (stopped after its header, step 8)");
        wr(7'h06, 8'h02);
        upset_to = 6;                                       // ERR CRC read: RDONE -> SDONE
        tx[0] = 8'h86; tx[1] = 0; tx[2] = 0; xfer(24);
        upset_to = -1;
        $display("ERR CRC read with the upset: MISO %02h %02h %02h, pop requests %0d, pops %0d, FRAME_ERR %0d, level %0d",
                 rx[0], rx[1], rx[2], n_preq, n_pop, n_ferr, dut.fifo_level);
        repeat (32768) @(posedge MCLK);
        smp(64, "read H (the next read)");
        $finish;
    end
endmodule
`default_nettype wire
