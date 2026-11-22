// tb_b31_crcoff - audit round 31 (B): the CRC-off operation (requirements 5.4 step 4's last item, round 30's 420): a
// one-bit header error in a host write lands silently on a register outside the remedy's read-back set (shadows
// 0x20-0x28 and timers 0x50-0x54, read twice before every START / APPLY / APPLY_NR).
// Case A: step 3's mandated ALERT_MASK_D = 0x00 write, header bit 0 flipped -> [0x08, 0x00]: ALERT_MASK = 0x00.
// Case B: T_ELEC = 13 ms, header bit 2 flipped -> [0x55, 0x0D]: IF_CFG = 0x01, CRC_EN = 1.
// Case C: T_WARM = 17 ms, header bit 6 flipped -> [0x10, 0x11]: START in IDLE.
`timescale 1ns / 1ps
`default_nettype none
module tb_b31_crcoff;
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
    logic [7:0] e, v1, v2;
    task automatic wr_hdr_err(input logic [7:0] hdr_sent, input logic [7:0] flip, input logic [7:0] val);
        spi_tx[0] = hdr_sent ^ flip; spi_tx[1] = val; spi_xfer(2, 0);      // CRC off: 2 bytes
        $display("  write [0x%02h,0x%02h] arrives as [0x%02h,0x%02h]: MISO %02h %02h (rule (a) %s)", hdr_sent, val,
                 spi_tx[0], val, spi_rx[0], spi_rx[1], (spi_rx[0][7:6] == 2'b10 && spi_rx[1] == 8'h00) ? "passes" : "fails");
    endtask
    task automatic burst(input logic [6:0] a, input integer n);      // CRC-off burst read, n data bytes
        spi_tx[0] = {1'b1, a}; for (int i = 1; i <= n; i++) spi_tx[i] = 8'h00;
        spi_xfer(n + 1, 0);
    endtask
    task automatic reset_chip();
        RESET_N = 1'b0; bfm_crc_en = 1'b0; repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
    endtask
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        // ---------------------------------------------------------------- case A
        $display("case A (CRC off): step 3's ALERT_MASK_D = 0x00");
        r14_write(7'h06, 8'h01);
        wr_hdr_err(8'h09, 8'h01, 8'h00);
        r14_read(7'h06, e); $display("  ERR read 0x%02h", e);
        r14_read(7'h09, v1); r14_read(7'h09, v2);
        $display("  read-back ALERT_MASK_D %02h, %02h (written 0x00): the host writes it again", v1, v2);
        r14_write(7'h09, 8'h00);
        r14_read(7'h09, v1); r14_read(7'h09, v2); $display("  read-back ALERT_MASK_D %02h, %02h: done", v1, v2);
        burst(7'h20, 9); $write("  remedy read-back 0x20-0x28:"); for (int i = 1; i <= 9; i++) $write(" %02h", spi_rx[i]); $display("");
        burst(7'h50, 5); $write("  remedy read-back 0x50-0x54:"); for (int i = 1; i <= 5; i++) $write(" %02h", spi_rx[i]); $display("");
        // a frame error (a sample read the chip counts 65 pulses of): ALERT in the next STATUS
        spi_tx[0] = SMP_HDR; for (int i = 1; i < 8; i++) spi_tx[i] = 8'h00; spi_xfer(8, 1);
        r14_read(7'h03, v1);
        $display("  after a FRAME_ERR: next STATUS 0x%02h (ALERT %0d), ERR 0x%02h, chip ALERT_MASK 0x%02h, ALERT_MASK_D 0x%01h",
                 spi_status, spi_status[5], dut.u_regs.err, dut.u_regs.r_mask, dut.u_regs.r_mask_d);
        // ---------------------------------------------------------------- case B
        reset_chip();
        $display("case B (CRC off): T_ELEC = 13 ms");
        wr_hdr_err(8'h51, 8'h04, 8'h0D);
        r14_read(7'h06, e); $display("  ERR read 0x%02h (3-byte read; chip IF_CFG now 0x%01h)", e, {dut.u_regs.r_drdy, dut.u_regs.r_crc});
        for (int k = 1; k <= 3; k++) begin
            r14_read(7'h51, v1); r14_read(7'h51, v2);
            $display("  pass %0d: read-back T_ELEC %02h, %02h (3rd bytes %02h): rewrite [0x51,0x0D]", k, v1, v2, spi_rx[2]);
            r14_write(7'h51, 8'h0D);
            r14_read(7'h06, e);
            $display("    MISO of the rewrite passed rule (a); ERR read 0x%02h; chip ERR 0x%02h, T_ELEC 0x%02h", e, dut.u_regs.err, dut.u_regs.r_te);
        end
        burst(7'h50, 5); $write("  remedy read-back 0x50-0x54:"); for (int i = 1; i <= 5; i++) $write(" %02h", spi_rx[i]); $display("");
        // ---------------------------------------------------------------- case C
        reset_chip();
        $display("case C (CRC off): T_WARM = 17 ms, in IDLE before the offset DAC is written");
        wr_hdr_err(8'h50, 8'h40, 8'h11);
        repeat (600) @(negedge MCLK);
        r14_read(7'h04, v1); $display("  STATE %0d, AFE_RST %0d, ERR 0x%02h (the host thinks IDLE)", v1, AFE_RST, dut.u_regs.err);
        $finish;
    end
endmodule
