// tb_b24_pend - audit round 24, auditor B: the CMD_PENDING wait of 5.4 (b)/(d) at 64 kHz, 1 MHz SCLK, 5 us between frames.
// A FLUSH in RUN committed just after a tick (the next tick 15.2 us later, as the bound's "16 frames"), then CRC reads of
// STATUS until two consecutive CRC-valid reads show CMD_PENDING = 0. Run 0: no fault. Run 1: the chip counts one extra
// SCLK pulse before host pulse 9 of the third read (one slip).
`timescale 1ns / 1ps
`default_nettype none
module tb_b24_pend;
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

    // a 3-byte transfer; extra_after >= 0: the chip sees one more pulse 150 ns into the low phase after host pulse
    // extra_after (it reads MOSI bit extra_after + 1 twice and the host skips one of its bits)
    task automatic xfer3(input integer extra_after);
        integer total;
        total = 24;
        CS_N = 1'b0;
        MOSI = spi_bit(0, 3);
        #(spi_tcss);
        for (int n = 0; n < total; n++) begin
            SCLK = 1'b1; spi_rx[n / 8][7 - (n % 8)] = miso_pad; #(spi_high); SCLK = 1'b0;
            MOSI = (n + 1 < total) ? spi_bit(n + 1, 3) : 1'b0;
            if (n == extra_after) begin #(150.0); SCLK = 1'b1; #(100.0); SCLK = 1'b0; #(spi_low - 250.0); end
            else if (n + 1 < total) #(spi_low);
        end
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
    endtask

    real t_cmd, t_acc, t_rd;
    integer nreads, zeros, run;
    logic [7:0] v;
    task automatic wait_pending(input integer slip_read, output integer n, output real t_ok);
        logic [7:0] c;
        n = 0; zeros = 0;
        while (zeros < 2 && n < 12) begin
            spi_tx[0] = 8'h83; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
            n = n + 1;
            xfer3((n == slip_read) ? 8 : -1);
            c = tb_crc8_update(tb_crc8_update(8'h00, 8'h83), spi_rx[1]);
            if (c !== spi_rx[2] || spi_rx[0][7:6] !== 2'b10) begin
                $display("  read %0d: %02h %02h %02h  CRC or rule (a) fails", n, spi_rx[0], spi_rx[1], spi_rx[2]);
                zeros = 0;
            end else begin
                $display("  read %0d: %02h %02h %02h  CRC ok, CMD_PENDING %0d (ends %0.1f us after the command)", n,
                         spi_rx[0], spi_rx[1], spi_rx[2], spi_rx[1][4], ($realtime - spi_tidle - t_cmd) / 1000.0);
                zeros = spi_rx[1][4] ? 0 : zeros + 1;
            end
        end
        t_ok = $realtime - spi_tidle;
    endtask

    initial begin
        spi_high = 500.0; spi_low = 500.0; spi_tcss = 1000.0; spi_tcsh = 200.0; spi_tidle = 5000.0;  // 1 MHz, 5 us gaps
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (20) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;                 // CRC on
        r14_write(7'h26, 8'h00);                                    // CHOP_FAST 0: 64 kHz
        r14_write(7'h52, 8'd29);                                    // T_REC minimum
        r14_cmd(8'h11);                                             // START
        while (dut.seq_state !== ST_RUN) @(posedge MCLK);
        repeat (40000) @(posedge MCLK);
        r14_read(7'h06, v); r14_write(7'h06, v);                    // clear ERR
        for (run = 0; run < 2; run++) begin
            // read the FIFO empty so STATUS is 0x88 (RUN, no data, no alert)
            begin logic [7:0] s; logic [15:0] q; logic [23:0] dd; bit ok;
                repeat (12) begin r14_sample(s, q, dd, ok); if (s[7] == 1'b0) break; end end
            r14_read(7'h06, v); if (v != 8'h00) r14_write(7'h06, v);
            // the FLUSH frame timed so its commit lands just after a tick: the next tick ~15.2 us later
            @(posedge dut.tick);
            #(2.0 * 15625.0 - (spi_tcss + 24.0 * 1000.0 - 500.0 + spi_tcsh) + 300.0);
            spi_tx[0] = 8'h10; spi_tx[1] = 8'h55; spi_tx[2] = tb_crc8_update(tb_crc8_update(8'h00, 8'h10), 8'h55);
            begin integer total; total = 24; CS_N = 1'b0; MOSI = spi_bit(0, 3); #(spi_tcss);
                for (int n = 0; n < total; n++) begin
                    SCLK = 1'b1; spi_rx[n / 8][7 - (n % 8)] = miso_pad; #(spi_high); SCLK = 1'b0;
                    MOSI = (n + 1 < total) ? spi_bit(n + 1, 3) : 1'b0; if (n + 1 < total) #(spi_low);
                end
                #(spi_tcsh); CS_N = 1'b1; t_cmd = $realtime; #(spi_tidle); end
            fork begin @(posedge dut.cmd_ack); $display("  (the tick takes the FLUSH %0.1f us after the command's CS_N rise)", ($realtime - t_cmd) / 1000.0); end join_none
            $display("run %0d (%s):", run, run ? "one SCLK slip in read 3" : "no fault");
            wait_pending(run ? 3 : -1, nreads, t_acc);
            $display("  -> CMD_PENDING = 0 accepted after %0d reads, %0.1f us after the command's CS_N rise", nreads, (t_acc - t_cmd) / 1000.0);
            t_rd = (t_acc - t_cmd) / nreads / 1000.0;
            $display("  -> the (d) bound, 15.6 us + 4 reads of %0.1f us each (frame and 5 us gap): %0.1f us", t_rd, 15.6 + 4.0 * t_rd);
            r14_read(7'h06, v); $display("  ERR now 0x%02h", v); if (v != 8'h00) r14_write(7'h06, v);
            repeat (20000) @(posedge MCLK);
        end
        $finish;
    end
endmodule
`default_nettype wire
