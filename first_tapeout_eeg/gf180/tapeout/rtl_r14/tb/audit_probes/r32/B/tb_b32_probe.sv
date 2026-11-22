// tb_b32_probe - audit round 32 (B): the CRC-mode probe of host step 9 ([0xD5, 0x00, 0x00]) sent to a chip with CRC
// on, with one SCLK fault of each of the four kinds at every pulse k. A host view of [bit 0 of byte 2 = 0, byte 3 =
// 0x00, STATUS bits 7..6 = 10] is the probe's "CRC off" answer. T_REC and T_RST are set to the values the slip model
// flags (0x30 and 0x22) and then to their defaults (0x20, 0x0D).
`timescale 1ns / 1ps
`default_nettype none
module tb_b32_probe;
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
    // kind 0 missed pulse k (an 8 ns runt right after an MCLK edge), 1 extra pulse in the low phase before pulse k,
    // 2 bounce in pulse k's high phase, 3 pulses k and k+1 merged (the low phase between them lost)
    task automatic xfer_fault(input logic [23:0] tx, input integer kind, input integer k, output logic [23:0] rx);
        CS_N = 1'b0;
        MOSI = tx[23];
        #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            if (kind == 1 && n == k) begin            // the extra pulse (100 ns high), then a normal low phase
                if (n == 0) #(0.0);
                SCLK = 1'b1; #(100.0); SCLK = 1'b0; #(spi_low);
            end
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
    logic [23:0] rx;
    logic [7:0] v;
    integer nhit, ntot;
    string kn [0:3] = '{"miss", "extra", "bounce", "merge"};
    task automatic sweep(input string tag);
        logic [7:0] s, d, c;
        for (int kind = 0; kind < 4; kind++)
            for (int k = 0; k < (kind == 3 ? 23 : 24); k++) begin
                xfer_fault(24'hD50000, kind, k, rx);
                s = rx[23:16]; d = rx[15:8]; c = rx[7:0];
                ntot++;
                if (s[7:6] == 2'b10 && d[0] == 1'b0 && c == 8'h00) begin
                    nhit++;
                    $display("%s: %s at pulse %0d -> host sees %02h %02h %02h: the probe's CRC-off answer (chip CRC_EN %0d, ERR %02h)",
                             tag, kn[kind], k, s, d, c, dut.crc_en, dut.u_regs.err);
                end
                r14_write(7'h06, 8'hFE);              // clear what the faulted frame set
            end
    endtask
    initial begin
        spi_high = 500.0; spi_low = 500.0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        nhit = 0; ntot = 0;
        r14_write(7'h52, 8'h30);                      // T_REC 48 (375 us)
        r14_read(7'h52, v); $display("T_REC %02h, T_RST %02h, CRC_EN %0d", dut.u_regs.r_trec, dut.u_regs.r_trst, dut.crc_en);
        sweep("T_REC 0x30");
        r14_write(7'h52, 8'h20); r14_write(7'h54, 8'h22);   // T_REC default, T_RST 34 (265.6 us)
        r14_read(7'h54, v); $display("T_REC %02h, T_RST %02h", dut.u_regs.r_trec, dut.u_regs.r_trst);
        sweep("T_RST 0x22");
        r14_write(7'h54, 8'h0D);                      // defaults
        sweep("defaults");
        $display("tb_b32_probe: %0d faulted probes, %0d read as CRC off with CRC on; %0d SPI timing notes", ntot, nhit,
                 spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
