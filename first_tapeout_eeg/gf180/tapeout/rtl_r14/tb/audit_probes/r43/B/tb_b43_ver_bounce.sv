// Audit 43 B: a CRC read of VERSION (0x81) with one SCLK bounce inside pulse 0's high phase, while the FIFO's head is a
// stored sample. regmap.slip_hazards models the chip's 4th MISO byte as 0x00; for a header the chip decodes as the
// sample window it is SEQ_L. Prediction: with the head word {0x88, SEQ 0x69xx (xx >= 0x80), DATA} the host receives
// [STATUS', 0x10, 0xD3] = a CRC-valid VERSION 0x10 while the chip did a (short, unpopped) sample read.
`timescale 1ns / 1ps
`default_nettype none
module tb_b43_ver_bounce;
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

    // spi_xfer with a bounce in pulse `at`'s high phase (the chip counts two pulses, MOSI unchanged)
    task automatic xfer_bounce(input integer nbytes, input integer at);
        integer total;
        total = 8 * nbytes;
        CS_N = 1'b0;
        MOSI = spi_bit(0, nbytes);
        #(spi_tcss);
        for (int n = 0; n < total; n++) begin
            SCLK = 1'b1;
            spi_rx[n / 8][7 - (n % 8)] = miso_pad;
            if (n == at) begin
                #(100.0); SCLK = 1'b0; #(100.0); SCLK = 1'b1; #(120.0);
            end else #(spi_high);
            SCLK = 1'b0;
            MOSI = (n + 1 < total) ? spi_bit(n + 1, nbytes) : 1'b0;
            if (n + 1 < total) #(spi_low);
        end
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
    endtask

    integer errors = 0;
    logic [7:0] v, e;
    logic [3:0] lvl;
    logic [47:0] w;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;          // CRC on
        r14_write(7'h06, 8'hFF);                             // RESET_FLAG off: ALERT 0
        r14_cmd(8'h11);                                      // START
        wait (dut.seq_state == ST_RUN);
        @(posedge dut.push_ok); @(posedge MCLK); #1;
        // the head: a stored sample with ERR (status 0x88), SEQ 0x69C3, any DATA (the FIFO's storage, deposited)
        w = {8'h88, 16'h69C3, 24'h5A5A5A};
        dut.u_fifo.mem[dut.u_fifo.rd_ptr] = w;
        lvl = dut.fifo_level;
        spi_tx[0] = 8'h81; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
        xfer_bounce(3, 0);
        $display("host received %02h %02h %02h; CRC8(0x81, byte 2) = %02h; chip header %02h; FIFO level %0d -> %0d",
                 spi_rx[0], spi_rx[1], spi_rx[2], tb_crc8_update(tb_crc8_update(8'h00, 8'h81), spi_rx[1]),
                 dut.u_spi.hdr, lvl, dut.fifo_level);
        if (spi_rx[0][7:6] === 2'b10 && spi_rx[2] === tb_crc8_update(tb_crc8_update(8'h00, 8'h81), spi_rx[1]))
            $display("RESULT: the host accepts VERSION 0x%02h (rule (a) and the CRC hold) from a chip that decoded 0x%02h", spi_rx[1], dut.u_spi.hdr);
        else
            $display("RESULT: rejected by the host");
        r14_read(7'h06, e);
        $display("ERR after it: %02h (FRAME_ERR expected); the next sample read:", e);
        begin
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
            r14_sample(st, sq, d, ok);
            $display("  status %02h SEQ %04h DATA %06h CRC ok %0b (the deposited word, not popped by the bounced read)", st, sq, d, ok);
        end
        $finish;
    end
    initial begin #(40.0e6); $display("FAIL: watchdog"); $finish; end
endmodule
`default_nettype wire
