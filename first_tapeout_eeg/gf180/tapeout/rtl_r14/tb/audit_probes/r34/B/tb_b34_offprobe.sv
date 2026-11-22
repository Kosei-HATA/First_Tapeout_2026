// tb_b34_offprobe - audit round 34 (B): the CRC-mode probe [0xD5, 0x00, 0x00] sent to a CRC-OFF chip whose settings
// are NOT all at their reset values, as one fault in step 3's first (CRC-off) IF_CFG write leaves them: the write
// landed on T_ELEC (header 0x55 -> 0x51, value 0x01 or 0x03), or its data lost bit 0 (0x03 -> 0x02: CRC off with
// DRDY_MODE 1). One SCLK fault of each of the four kinds at every pulse, and each of the 8 header bits flipped on MOSI.
// A host view [STATUS bits 7..6 = 10, bit 0 of byte 2 = 1, byte 3 = CRC-8(0xD5, byte 2)] is the CRC-ON answer.
`timescale 1ns / 1ps
`default_nettype none
module tb_b34_offprobe;
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
    task automatic xfer_fault(input logic [23:0] tx, input integer kind, input integer k, output logic [23:0] rx);
        CS_N = 1'b0;
        MOSI = tx[23];
        #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            if (kind == 1 && n == k) begin SCLK = 1'b1; #(100.0); SCLK = 1'b0; #(spi_low); end
            if (kind == 0 && n == k) begin
                @(posedge MCLK); #2.0;
                SCLK = 1'b1; rx[23 - n] = miso_pad; #8.0; SCLK = 1'b0;
                #(spi_high - 10.0);
            end else begin
                SCLK = 1'b1;
                rx[23 - n] = miso_pad;
                if (kind == 2 && n == k) begin
                    #(3.0 * TMCLK); SCLK = 1'b0; #(2.0 * TMCLK); SCLK = 1'b1; #(3.0 * TMCLK);
                end else #(spi_high);
                if (!(kind == 3 && n == k)) SCLK = 1'b0;
            end
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 < 24) #(spi_low);
        end
        SCLK = 1'b0;
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
    endtask
    function automatic logic [7:0] c8(input logic [7:0] a, input logic [7:0] b);
        return tb_crc8_update(tb_crc8_update(8'h00, a), b);
    endfunction
    logic [23:0] rx;
    integer nhit, ntot;
    task automatic judge(input string tag, input string what);
        logic [7:0] s, d, c;
        s = rx[23:16]; d = rx[15:8]; c = rx[7:0];
        ntot++;
        if (s[7:6] == 2'b10 && d[0] == 1'b1 && c == c8(8'hD5, d)) begin
            nhit++;
            $display("%s: %s -> host sees %02h %02h %02h: a CRC-ON answer from a CRC-off chip", tag, what, s, d, c);
        end
    endtask
    task automatic sweep(input string tag);
        for (int kind = 0; kind < 4; kind++)
            for (int k = 0; k < (kind == 3 ? 23 : 24); k++) begin
                xfer_fault(24'hD50000, kind, k, rx);
                judge(tag, $sformatf("SCLK kind %0d pulse %0d", kind, k));
            end
        for (int b = 0; b < 8; b++) begin
            xfer_fault(24'hD50000 ^ (24'h010000 << b), 9, 99, rx);   // kind 9: no SCLK fault, a header bit flipped
            judge(tag, $sformatf("header bit %0d flipped", b));
        end
        xfer_fault(24'hD50000, 9, 99, rx);
        $display("%s: unfaulted probe -> %02h %02h %02h (CRC_EN %0d, IF_CFG %02h, T_ELEC %02h)", tag, rx[23:16], rx[15:8],
                 rx[7:0], dut.crc_en, {dut.u_regs.r_drdy, dut.u_regs.r_crc}, dut.u_regs.r_te);
    endtask
    initial begin
        spi_high = 500.0; spi_low = 500.0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        nhit = 0; ntot = 0;
        r14_write(7'h51, 8'h01);                       // the IF_CFG write [0x55, 0x01] landed on T_ELEC (0x51)
        sweep("CRC off, T_ELEC 0x01");
        r14_write(7'h51, 8'h03);                       // [0x55, 0x03] landed on T_ELEC
        sweep("CRC off, T_ELEC 0x03");
        r14_write(7'h51, 8'h00); r14_write(7'h55, 8'h02);   // [0x55, 0x03] with bit 0 lost: CRC off, DRDY_MODE 1
        sweep("CRC off, IF_CFG 0x02");
        $display("tb_b34_offprobe: %0d faulted probes of a CRC-off chip, %0d read as CRC on; %0d SPI notes", ntot, nhit, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
