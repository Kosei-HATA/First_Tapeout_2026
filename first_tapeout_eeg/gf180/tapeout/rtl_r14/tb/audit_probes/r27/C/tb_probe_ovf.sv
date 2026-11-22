`timescale 1ns / 1ps
`default_nettype none
// probe: an illegal SPI state value forced inside the data byte of a write (as tb_top_r14 does for 11..15), here for
// every value 9..15; prints ERR and whether the write was committed
module tb_probe_ovf;
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
    `include "spi_bfm_r14.svh"
    logic [7:0] e, c;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        r14_write(7'h06, 8'hFF);
        for (int bad = 9; bad < 16; bad++) begin
            fork
                begin spi_tx[0] = 8'h24; spi_tx[1] = 8'h0E; spi_xfer(2, 0); end
                begin
                    #(6000.0);
                    case (bad)
                        9:       force dut.u_spi.st = 4'd9;
                        10:      force dut.u_spi.st = 4'd10;
                        11:      force dut.u_spi.st = 4'd11;
                        12:      force dut.u_spi.st = 4'd12;
                        13:      force dut.u_spi.st = 4'd13;
                        14:      force dut.u_spi.st = 4'd14;
                        default: force dut.u_spi.st = 4'd15;
                    endcase
                    @(posedge MCLK);
                    release dut.u_spi.st;
                end
            join
            r14_read(7'h06, e);
            r14_read(7'h24, c);
            $display("state value %0d forced in the data byte: ERR 0x%02h (FRAME_ERR %b), CPF_TRIM 0x%02h (%s)", bad, e,
                     e[1], c, c == 8'h0E ? "written" : "not written");
            r14_write(7'h06, 8'hFF);
            r14_write(7'h24, 8'h08);
        end
        $finish;
    end
endmodule
`default_nettype wire
