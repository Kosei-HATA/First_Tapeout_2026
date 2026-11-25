// audit round 44, B: a frame that sets FRAME_ERR (sample read with one extra SCLK pulse after its 64th bit: the host's
// copy is right, the chip flags OVF), then CS_N high for exactly 4 MCLK (+ phase in 1/8 MCLK steps), then the next frame:
// does that frame's header STATUS already carry ALERT (FRAME_ERR)?  Also with a CRC write with a wrong CRC (CRC_ERR)
// and an extra-pulse write (FRAME_ERR, write not committed, MISO 00 00 passes rule (a)).
`timescale 1ns / 1ps
`default_nettype none
module tb_c45_minhigh;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"
    // a raw frame with an optional extra SCLK pulse after the last bit, ending with CS_N high for tgap
    task automatic xfer_x(input integer nbytes, input bit extra, input real tgap);
        integer total; total = 8 * nbytes;
        CS_N = 1'b0; MOSI = spi_bit(0, nbytes); #(spi_tcss);
        for (int n = 0; n < total; n++) begin
            SCLK = 1'b1; spi_rx[n / 8][7 - (n % 8)] = miso_pad; #(spi_high);
            SCLK = 1'b0; MOSI = (n + 1 < total) ? spi_bit(n + 1, nbytes) : 1'b0; if (n + 1 < total) #(spi_low);
        end
        if (extra) begin #(spi_low); SCLK = 1'b1; #(spi_high); SCLK = 1'b0; end
        #(spi_tcsh); CS_N = 1'b1; #(tgap);
    endtask
    integer errs = 0, n = 0;
    logic [7:0] v, st2;
    initial begin
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (20) @(negedge MCLK);
        bfm_crc_en = 1'b0;
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;              // CRC on
        r14_read(7'h06, v); r14_write(7'h06, v);                // clear RESET_FLAG
        r14_read(7'h06, v); if (v !== 8'h00) begin $display("setup ERR %02h", v); errs++; end
        for (int kind = 0; kind < 1; kind++) begin
            for (int ph = 0; ph < 28; ph++) begin
                real gap; gap = 1.5 * TMCLK + ph * TMCLK / 8.0 + 0.01;
                // the faulty frame
                if (kind == 0) begin                                   // sample read + 1 extra pulse
                    spi_tx[0] = SMP_HDR; for (int i = 1; i < 8; i++) spi_tx[i] = 8'h00; xfer_x(8, 1, gap);
                end else if (kind == 1) begin                          // CRC write, wrong CRC
                    spi_tx[0] = 8'h24; spi_tx[1] = 8'h08; spi_tx[2] = tb_crc8_update(tb_crc8_update(0, 8'h24), 8'h08) ^ 8'h01;
                    xfer_x(3, 0, gap);
                end else begin                                         // CRC write + 1 extra pulse
                    spi_tx[0] = 8'h24; spi_tx[1] = 8'h08; spi_tx[2] = tb_crc8_update(tb_crc8_update(0, 8'h24), 8'h08);
                    xfer_x(3, 1, gap);
                end
                // the next frame: a header-only STATUS poll; its first byte
                spi_tx[0] = 8'h83; xfer_x(1, 0, 600.0);
                st2 = spi_rx[0]; n++;
                if (st2[STATUS_ALERT_LSB] !== 1'b1) begin
                    errs++; $display("gap %0.3f MCLK: next header 0x%02h without ALERT", gap / TMCLK, st2);
                end
                r14_read(7'h06, v);
                if (v !== (kind == 1 ? 8'h04 : 8'h02)) begin errs++; $display("kind %0d phase %0d: ERR 0x%02h", kind, ph, v); end
                r14_write(7'h06, v);
            end
        end
        $display("tb_b44_minhigh: %0d frame pairs, %0d errors, %0d SPI errors", n, errs, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
