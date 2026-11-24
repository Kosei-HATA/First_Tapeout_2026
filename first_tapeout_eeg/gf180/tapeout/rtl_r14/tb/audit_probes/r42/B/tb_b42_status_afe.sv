// tb_b42_status_afe - audit round 42, auditor B: rule (c)'s trigger 3 confirms AFE_RST = 1 "with the CRC reads above"
// (STATUS 0x03, STATE 0x04, ERR 0x06); only STATUS carries AFE_RST. RTL, CRC on, ALERT_MASK_D 0 (step 3), RUN with an
// overload standing (OVL_NOW 1) and the FIFO empty: STATUS 0x8A. The CRC STATUS read [0x83, 0, 0] with SCLK pulse k
// (k = 9, 10, 11) too short for the chip (one missed pulse, regmap.slip_hazards' first kind).
`timescale 1ns / 1ps
`default_nettype none
module tb_b42_status_afe;
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
    bit ovl = 1'b0;
    always @(posedge MCLK) CODE <= ovl ? 5'd31 : 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"
    logic [7:0] v, sst; logic [15:0] sq; logic [23:0] dt; bit ok;
    task automatic readout();
        forever begin
            r14_sample(sst, sq, dt, ok);
            if (ok && !sst[SMP_VALID_LSB] && spi_status[STATUS_DATA_LSB] == 1'b0) break;
        end
    endtask
    // a 3-byte CRC read whose pulse `miss` is a runt between two MCLK rising edges (the chip does not see it)
    task automatic read_missed(input logic [7:0] hdr, input integer miss, output logic [7:0] b0, b1, b2);
        logic [23:0] tx, rx;
        tx = {hdr, 16'h0000};
        CS_N = 1'b0; MOSI = tx[23];
        #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            if (n == miss) begin
                @(posedge MCLK); #3.0;
                SCLK = 1'b1; rx[23 - n] = miso_pad; #8.0; SCLK = 1'b0;
            end else begin
                SCLK = 1'b1; rx[23 - n] = miso_pad; #(spi_high); SCLK = 1'b0;
            end
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 < 24) #(spi_low);
        end
        #(spi_tcsh); CS_N = 1'b1; #(spi_tidle);
        b0 = rx[23:16]; b1 = rx[15:8]; b2 = rx[7:0];
    endtask
    initial begin #(200e6); $display("FAIL: watchdog"); $finish; end
    initial begin
        logic [7:0] h0, d, c;
        spi_high = 500.0; spi_low = 500.0;                                 // 1 MHz
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);                                            // step 2: RESET_FLAG cleared (CRC off)
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;                          // step 3: CRC on
        r14_write(7'h09, 8'h00);                                            // ALERT_MASK_D 0
        r14_write(7'h52, 8'd29);
        r14_write(7'h10, 8'h11);                                            // START
        while (dut.seq_state !== ST_RUN) @(posedge MCLK);
        for (int miss = 9; miss <= 11; miss++) begin
            @(negedge DRDY_N); readout();                                   // FIFO empty right after an output time
            ovl = 1'b1; repeat (12 * 32) @(posedge MCLK);                   // an overload standing through the reads
            r14_read(7'h06, v);                                             // ERR before (CRC read)
            $display("before: STATE %0d, AFE_RST pin %b, OVL_NOW %b, FIFO level %0d, ERR 0x%02h, STATUS register 0x%02h",
                     dut.seq_state, AFE_RST, dut.ovl_now, dut.fifo_level, v, dut.status_byte);
            read_missed(8'h83, miss, h0, d, c);
            $display("CRC STATUS read, chip misses pulse %0d: host gets %02h %02h %02h, CRC %s, fixed bits %s -> READY %0d DATA %0d AFE_RST %0d (chip: STATE %0d, AFE_RST pin %b)",
                     miss, h0, d, c, (c == tb_crc8_update(tb_crc8_update(8'h00, 8'h83), d)) ? "valid" : "bad",
                     (d[7:6] == 2'b10 && h0[7:6] == 2'b10) ? "ok" : "bad", d[STATUS_READY_LSB], d[STATUS_DATA_LSB],
                     d[STATUS_AFE_RST_LSB], dut.seq_state, AFE_RST);
            r14_read(7'h06, v);
            ovl = 1'b0;
            $display("ERR after: 0x%02h (FRAME_ERR %0d)", v, v[ERR_FRAME_ERR_LSB]);
            r14_write(7'h06, v); r14_write(7'h07, 8'h03);                  // clear (the bench's own housekeeping)
        end
        $display("tb_b42_status_afe done: %0d SPI errors", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
