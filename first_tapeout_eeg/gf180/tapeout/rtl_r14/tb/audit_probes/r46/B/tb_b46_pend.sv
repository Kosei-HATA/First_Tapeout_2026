// tb_b46_pend - audit round 46, auditor B: (1) which writes the chip commits while a command is pending (CRC on,
// 64 kHz, a FLUSH committed just after a tick), against requirements 5.0's generated sentence "書き込みの確定は ...
// （前の命令が未処理なら確定しない）"; (2) the rise instants of FRAME_ERR, the read header's ADDR_ERR and OVERRUN
// against spec 3.2 / FLG-02.
`timescale 1ns / 1ps
`default_nettype none
module tb_b46_pend;
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

    // what eeg_regs saw at the commit cycle of the last write
    logic       c_busy, c_pend, c_wok, c_soft; logic [7:0] c_ev; integer n_we = 0;
    always @(posedge MCLK) if (dut.reg_we) begin
        c_pend = dut.u_regs.pend; c_busy = dut.u_regs.pend && !dut.cmd_ack; c_wok = dut.u_regs.w_ok;
        c_soft = dut.u_regs.soft_reset; c_ev = dut.u_regs.ev_err; n_we = n_we + 1;
    end
    integer bad = 0;
    task automatic one(input logic [6:0] a, input logic [7:0] v, input string name);
        logic [7:0] e;
        @(posedge dut.tick); #(4000.0); spi_tidle = 125.0;
        r14_cmd(8'h55);                                  // FLUSH, committed just after the next tick
        r14_write(a, v);                                 // committed while the FLUSH waits for its tick
        spi_tidle = 600.0;
        $display("%-26s pend=%0d busy(pend&!ack)=%0d committed(w_ok)=%0d soft_reset=%0d ev_err=0x%02h",
                 name, c_pend, c_busy, c_wok, c_soft, c_ev);
        if (!c_pend) bad = bad + 1;
        if (c_soft) begin #(2000.0); bfm_crc_en = 1'b0; r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1; end
        r14_read(7'h06, e); r14_write(7'h06, e);         // clear what the case left
    endtask

    real t_csr, t_rise; integer cyc_hdr, cyc_err, cyc_store, cyc_ovr, cyc;
    always @(posedge MCLK) cyc = cyc + 1;
    initial begin
        logic [7:0] v; logic [7:0] ss; logic [15:0] sq; logic [23:0] dd; bit ok;
        cyc = 0;
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;     // CRC on (step 3)
        r14_read(7'h06, v); r14_write(7'h06, v);
        r14_write(7'h26, 8'h00); r14_cmd(8'h33); #(100000.0);   // 64 kHz (IDLE APPLY)
        r14_read(7'h06, v); r14_write(7'h06, v);
        r14_write(7'h11, 8'h3C);                         // key open (DEBUG is a test register)
        $display("--- (1) writes committed while a FLUSH is pending (CRC on, 64 kHz) ---");
        one(7'h08, 8'h7F, "ALERT_MASK 0x08");
        one(7'h09, 8'h00, "ALERT_MASK_D 0x09");
        one(7'h55, 8'h03, "IF_CFG 0x55");
        one(7'h62, 8'h00, "DEBUG 0x62 (key open)");
        one(7'h06, 8'h00, "ERR 0x06 (W1C)");
        one(7'h07, 8'h00, "DFLAG 0x07 (W1C)");
        one(7'h11, 8'h3C, "TEST_KEY 0x11");
        one(7'h10, 8'h3C, "COMMAND unknown 0x3C");
        one(7'h10, 8'hA5, "COMMAND SOFT_RESET");
        one(7'h21, 8'h05, "OFF_M_L 0x21 (guarded)");
        one(7'h10, 8'h55, "COMMAND FLUSH (defined)");
        $display("cases without a pending command at the commit: %0d", bad);
        // --- (2) flag instants
        $display("--- (2) flag rise instants ---");
        // FRAME_ERR: a CRC-on write with 1 extra bit
        spi_tx[0] = 8'h28; spi_tx[1] = 8'h07; spi_tx[2] = tb_crc8_update(tb_crc8_update(8'h00, 8'h28), 8'h07);
        fork
            begin spi_xfer(3, 1); end
            begin @(posedge CS_N); t_csr = $realtime; @(posedge dut.u_regs.err[1]); t_rise = $realtime;
                  $display("FRAME_ERR rises %0.2f MCLK after the CS_N pin rise (spec 3.2: 3..4)", (t_rise - t_csr) / TMCLK); end
        join
        r14_read(7'h06, v); r14_write(7'h06, v);
        // read header with an undefined address
        fork
            begin spi_tx[0] = 8'hFE; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00; spi_xfer(3, 0); end
            begin
                do @(negedge MCLK); while (!(dut.u_spi.sclk_rise && dut.u_spi.bit_cnt == 3'd7 && dut.u_spi.st == 4'd1));
                cyc_hdr = cyc;                                    // the cycle in which the SPI takes the header (its end edge = cyc+1)
                @(posedge dut.u_regs.err[3]); #1 cyc_err = cyc;
                $display("read-header ADDR_ERR rises %0d edges after the edge that ends the header cycle (spec 3.2: 2 MCLK later)",
                         cyc_err - cyc_hdr);
            end
        join
        r14_read(7'h06, v); r14_write(7'h06, v);
        // OVERRUN: START (64 kHz), RUN, no reads for 10 outputs
        r14_cmd(8'h11);
        wait (dut.seq_state == 4'd6);
        fork
            begin
                do @(negedge MCLK); while (!(dut.seq_store && !dut.push_ok)); cyc_store = cyc;   // the dropped store's cycle
                @(posedge dut.u_regs.dflag[0]); #1 cyc_ovr = cyc;
                $display("DFLAG.OVERRUN rises %0d edges after the edge that ends the dropped store's cycle (spec 3.2: 1 MCLK later; FLG-02: that edge, no register between)",
                         cyc_ovr - cyc_store);
            end
        join
        $finish;
    end
    initial begin #(60.0e6); $display("watchdog"); $finish; end
endmodule
`default_nettype wire
