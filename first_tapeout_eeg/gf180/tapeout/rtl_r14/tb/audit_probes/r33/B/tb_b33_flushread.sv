// tb_b33_flushread - audit round 33 (B): a sample read that runs across the tick of a FLUSH (and of an APPLY in RUN).
// The chip copies the FIFO head at the header (a stored, VALID word with a correct CRC), the flush at the tick clears
// the copy's head mark, the 8-byte read is not popped (spec 3.2), and the FIFO is empty: the next read does NOT return
// the same SEQ (requirements 5.4 step 6 says a CRC-valid VALID word "was popped; if not, the next read returns the
// same SEQ"). CRC on, 1 MHz, 128 kHz chopper (tick every 7.8 us), default timers.
`timescale 1ns / 1ps
`default_nettype none
module tb_b33_flushread;
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
    integer n_snapflush = 0, n_pop = 0;
    logic snapped = 0;
    always @(posedge MCLK) begin
        if (dut.smp_snap) snapped <= 1'b1;
        if (dut.u_fifo.pop_ok) n_pop++;
    end
    logic [7:0] st, v, lvl;
    logic [15:0] sq, sq2;
    logic [23:0] dt;
    bit ok;
    task automatic one(input logic [7:0] code, input string tag);
        integer np0, x;
        logic [7:0] e;
        bit done;
        done = 0;
        for (x = 0; x < 32 && !done; x++) begin
            do r14_read(7'h04, v); while (v != ST_RUN);
            do r14_read(7'h05, lvl); while (lvl < 2);
            r14_read(7'h06, e); if (e != 8'h00) r14_write(7'h06, e);
            do @(posedge MCLK); while (!dut.tick);
            #(250.0 * x);
            np0 = n_pop;
            spi_high = 250.0; spi_low = 250.0; spi_tidle = 130.0; spi_tcss = 160.0;
            r14_cmd(code);                               // the command (CRC on) ...
            r14_sample(st, sq, dt, ok);                  // ... and at once a sample read (step 4 forbids this)
            spi_high = 500.0; spi_low = 500.0; spi_tidle = 600.0; spi_tcss = 300.0;
            repeat (20) @(posedge MCLK);
            if (ok && st[SMP_VALID_LSB] && n_pop == np0) begin
                done = 1;
                $display("%s (offset %0d ns after a tick): read across the tick: status %02h SEQ %0d CRC ok (VALID 1); popped %0d; FIFO_LEVEL now %0d; ERR %02h",
                         tag, 250 * x, st, sq, n_pop - np0, dut.fifo_level, dut.u_regs.err);
                r14_sample(st, sq2, dt, ok);
                $display("%s: next read: status %02h SEQ %0d CRC %0b (VALID %0b) -> %s", tag, st, sq2, ok, st[SMP_VALID_LSB],
                         (st[SMP_VALID_LSB] && sq2 == sq) ? "same SEQ" : "NOT the same SEQ: the VALID word was neither popped nor kept (flushed)");
            end
        end
        if (!done) $display("%s: no overlap found", tag);
    endtask
    initial begin
        spi_high = 500.0; spi_low = 500.0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h09, 8'h00);                         // ALERT_MASK_D 0 (step 3)
        r14_cmd(CMD_START);
        do r14_read(7'h04, v); while (v != ST_RUN);
        $display("RUN at %0t", $time);
        one(CMD_FLUSH, "FLUSH");
        one(CMD_APPLY, "APPLY in RUN");
        $display("tb_b33_flushread done; %0d SPI notes", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
