// tb_r15 - the r15 additions taken from the Test4-1 draft (11/27), at the pins of eeg_digital_top:
//   (a) VERSION 0x11; CFG_GEN, DROP_CNT and the LATEST window after a reset (0, 0, the empty word with its CRC);
//   (b) CFG_GEN: +1 at every load of the active copies (START, APPLY, APPLY_NR), counted against dut.apply;
//   (c) LATEST: the last pushed output (SEQ and DATA equal the monitor's last push), read twice the same, never popped
//       (FIFO_LEVEL unchanged apart from the pushes during the read), the empty word right after an apply, its CRC
//       started from LAT_HDR (a CRC started from SMP_HDR fails), and it follows the outputs while the FIFO is full;
//   (d) DROP_CNT: equal to the FIFO's drops (ovr_set pulses) since the last OVERRUN clear, back to 0 by the W1C of
//       DFLAG.OVERRUN (a write of DFLAG with OVERRUN 0 keeps it), stops at 255 (deposited at 253);
//   (e) SOFT_RESET: CFG_GEN 0, DROP_CNT 0, LATEST empty; with CRC on, every read checked by its CRC.
`timescale 1ns / 1ps
`default_nettype none

module tb_r15;
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
`ifdef FIFO4
    localparam int FD = 4;
`else
    localparam int FD = 8;
`endif
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(FD)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    `include "spi_bfm_r14.svh"

    integer errors = 0, checks = 0;
    task automatic fail(input string msg);
        errors = errors + 1;
        if (errors <= 30) $display("FAIL @%0t: %s", $time, msg);
    endtask
    task automatic expect8(input logic [7:0] got, input logic [7:0] want, input string what);
        checks = checks + 1;
        if (got !== want) fail($sformatf("%s: 0x%02h, expected 0x%02h", what, got, want));
    endtask

    // ---------------- monitors: applies, pushes (the last pushed word), drops since the last OVERRUN clear
    integer n_apply = 0, n_drop = 0;
    logic [15:0] last_seq;
    logic [23:0] last_data;
    logic        last_v = 1'b0;
    always @(posedge MCLK) begin
        if (dut.apply) n_apply <= n_apply + 1;
        // the OVERRUN clear from the committed write at the SPI's port (not the RTL's own drop_clr)
        if (dut.reg_we && dut.reg_addr == A_DFLAG && dut.reg_wdata[DFLAG_OVERRUN_LSB]) n_drop <= dut.ovr_set ? 1 : 0;
        else if (dut.ovr_set)    n_drop <= n_drop + 1;
        if (dut.apply)            last_v <= 1'b0;
        else if (dut.u_fifo.push) begin last_v <= 1'b1; last_seq <= dut.seq_cnt; last_data <= dut.cic_data; end
        else if (dut.seq_flush)   last_v <= 1'b0;
        if (!dut.rst_n) begin n_apply <= 0; n_drop <= 0; last_v <= 1'b0; end
    end

    // ---------------- the LATEST read: 8 bytes, CRC from LAT_HDR
    task automatic lat_read(output logic [7:0] st, output logic [15:0] sq, output logic [23:0] d,
                            output bit crc_ok, output bit crc_as_sample);
        logic [7:0] c, cs;
        spi_tx[0] = LAT_HDR;
        for (int i = 1; i < SMP_FRAME_LEN; i++) spi_tx[i] = 8'h00;
        spi_xfer(SMP_FRAME_LEN, 0);
        st = spi_rx[SMP_BYTE_SSTAT];
        sq = {spi_rx[SMP_BYTE_SEQ], spi_rx[SMP_BYTE_SEQ + 1]};
        d  = {spi_rx[SMP_BYTE_DATA], spi_rx[SMP_BYTE_DATA + 1], spi_rx[SMP_BYTE_DATA + 2]};
        c  = tb_crc8_update(8'h00, LAT_HDR);
        cs = tb_crc8_update(8'h00, SMP_HDR);
        for (int i = 1; i < SMP_BYTE_CRC; i++) begin c = tb_crc8_update(c, spi_rx[i]); cs = tb_crc8_update(cs, spi_rx[i]); end
        crc_ok = (c === spi_rx[SMP_BYTE_CRC]);
        crc_as_sample = (cs === spi_rx[SMP_BYTE_CRC]);
    endtask

    task automatic lat_expect(input string what);
        logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok, oks;
        logic v; logic [15:0] es; logic [23:0] ed;
        lat_read(st, sq, d, ok, oks);
        checks = checks + 1;
        // the monitor's word at the header's copy: the read takes ~4 us, an output every 1 ms; re-read if one came
        v = last_v; es = last_seq; ed = last_data;
        if (!ok) fail($sformatf("%s: LATEST CRC wrong", what));
        if (oks) fail($sformatf("%s: LATEST's CRC also passes as a sample's (from SMP_HDR)", what));
        if (st[SMP_VALID_LSB] !== v) fail($sformatf("%s: LATEST VALID %b, expected %b", what, st[SMP_VALID_LSB], v));
        if (v && (sq !== es || d !== ed))
            fail($sformatf("%s: LATEST SEQ %0d DATA %06h, expected %0d %06h", what, sq, d, es, ed));
        if (!v && (sq !== 16'h0 || d !== 24'h0)) fail($sformatf("%s: empty LATEST with SEQ %0d DATA %06h", what, sq, d));
    endtask

    task automatic rd(input logic [6:0] a, output logic [7:0] v);
        r14_read(a, v);
    endtask

    task automatic wait_run(input string what);
        real t0;
        t0 = $realtime;
        while (dut.seq_state !== ST_RUN && ($realtime - t0) < 60.0e6) @(posedge MCLK);
        if (dut.seq_state !== ST_RUN) fail($sformatf("%s: not in RUN", what));
    endtask

    task automatic wait_cmd_taken();
        while (dut.u_regs.pend !== 1'b0) @(posedge MCLK);
        repeat (4) @(posedge MCLK);
    endtask

    logic [7:0] v, lv0, lv1;
    integer a0, k, pushes;
    logic [7:0] st; logic [15:0] sq, sq2; logic [23:0] d, d2; bit ok, oks;
    initial begin
        repeat (20) @(posedge MCLK);
        RESET_N = 1'b1;
        repeat (200) @(posedge MCLK);

        // (a) after the reset
        rd(A_VERSION, v);  expect8(v, 8'h11, "VERSION");
        rd(A_CFG_GEN, v);  expect8(v, 8'h00, "CFG_GEN after reset");
        rd(A_DROP_CNT, v); expect8(v, 8'h00, "DROP_CNT after reset");
        lat_expect("LATEST after reset");
        r14_write(A_CFG_GEN, 8'h55);                    // read-only: ADDR_ERR, nothing written
        rd(A_CFG_GEN, v);  expect8(v, 8'h00, "CFG_GEN after a write");
        rd(A_ERR, v);      checks++; if (!v[ERR_ADDR_ERR_LSB]) fail("a write of CFG_GEN gave no ADDR_ERR");
        r14_write(A_ERR, 8'hFF);

        // (b) START: CFG_GEN 1
        r14_cmd(CMD_START);
        wait_cmd_taken();
        rd(A_CFG_GEN, v);  expect8(v, 8'(n_apply), "CFG_GEN after START"); expect8(v, 8'h01, "CFG_GEN = 1 after START");
        lat_expect("LATEST after START");
        wait_run("START");
        repeat (3) #1.0e6;
        // (c) LATEST: twice the same, no pop
        lv0 = dut.fifo_level; pushes = 0;
        fork
            begin lat_expect("LATEST in RUN (1)"); lat_expect("LATEST in RUN (2)"); end
            begin repeat (2000) begin @(posedge MCLK); if (dut.u_fifo.push_ok) pushes++; end end
        join
        lv1 = dut.fifo_level;
        checks++;
        if (lv1 !== 8'(lv0 + pushes) && lv1 !== 8'(FD)) fail($sformatf("LATEST reads changed FIFO_LEVEL %0d -> %0d (pushes %0d)", lv0, lv1, pushes));
        // a short sample read (CRC off: header and the status byte, no pop) marks the head as copied; a full LATEST
        // read after it must still pop nothing (eeg_fifo `held` cleared by lat_snap)
        spi_tx[0] = SMP_HDR; spi_tx[1] = 8'h00;
        spi_xfer(2, 0);
        lv0 = dut.fifo_level; pushes = 0;
        fork
            lat_expect("LATEST after a short sample read");
            begin repeat (1000) begin @(posedge MCLK); if (dut.u_fifo.push_ok) pushes++; end end
        join
        lv1 = dut.fifo_level;
        checks++;
        if (lv1 !== 8'(lv0 + pushes)) fail($sformatf("a LATEST read after a short sample read popped: FIFO_LEVEL %0d -> %0d (pushes %0d)", lv0, lv1, pushes));
        r14_sample(st, sq, d, ok);                      // the oldest: a different SEQ unless one sample
        checks++; if (!ok || !st[SMP_VALID_LSB]) fail("sample read in RUN");
        // (d) overflow: no reads for FD + 6 outputs
        repeat (FD + 6) #1.0e6;
        rd(A_DROP_CNT, v); expect8(v, 8'(n_drop), "DROP_CNT = drops");
        checks++; if (n_drop < 4) fail($sformatf("only %0d drops", n_drop));
        lat_expect("LATEST with the FIFO full (follows the dropped outputs)");
        r14_write(A_DFLAG, 8'h02);                      // OVL only: DROP_CNT kept
        rd(A_DROP_CNT, v); expect8(v, 8'(n_drop), "DROP_CNT after a DFLAG write without OVERRUN");
        r14_write(A_DFLAG, 8'h01);                      // OVERRUN: DROP_CNT 0 (or 1 if a drop came with it)
        rd(A_DROP_CNT, v); expect8(v, 8'(n_drop), "DROP_CNT after the OVERRUN clear");
        checks++; if (v > 8'd1) fail($sformatf("DROP_CNT %0d after the clear", v));
        // saturation: deposit 253, then three or more drops
        @(negedge MCLK); dut.u_regs.drop_cnt = 8'd253; n_drop = 253;
        repeat (4) #1.0e6;
        rd(A_DROP_CNT, v); expect8(v, 8'hFF, "DROP_CNT stops at 255");
        r14_write(A_DFLAG, 8'h01);
        // (b, c) APPLY in RUN: CFG_GEN + 1, LATEST empty right after the apply
        a0 = n_apply;
        r14_cmd(CMD_APPLY);
        while (n_apply == a0) @(posedge MCLK);
        lat_expect("LATEST right after APPLY");
        rd(A_CFG_GEN, v); expect8(v, 8'(n_apply), "CFG_GEN after APPLY"); expect8(v, 8'h02, "CFG_GEN = 2 after APPLY");
        wait_run("APPLY");
        repeat (2) #1.0e6;
        lat_expect("LATEST in RUN after APPLY");
        // APPLY_NR in RUN: one step of M within range 1
        r14_cmd(CMD_STOP); wait_cmd_taken();
        r14_write(A_OFF_CTRL, 8'h01); r14_write(A_OFF_M_L, 8'd10);
        r14_cmd(CMD_START); wait_cmd_taken(); wait_run("START 2");
        rd(A_CFG_GEN, v); expect8(v, 8'(n_apply), "CFG_GEN after START 2");
        r14_write(A_OFF_M_L, 8'd11);
        a0 = n_apply;
        r14_cmd(CMD_APPLY_NR);
        while (n_apply == a0) @(posedge MCLK);
        lat_expect("LATEST right after APPLY_NR");
        rd(A_CFG_GEN, v); expect8(v, 8'(n_apply), "CFG_GEN after APPLY_NR"); expect8(v, 8'h04, "CFG_GEN = 4");
        repeat (5) #1.0e6;
        lat_expect("LATEST after APPLY_NR");
        // FLUSH in IDLE: LATEST empty
        r14_cmd(CMD_STOP); wait_cmd_taken();
        lat_expect("LATEST after STOP (kept)");
        r14_cmd(CMD_FLUSH); wait_cmd_taken();
        lat_expect("LATEST after FLUSH");
        checks++; if (last_v) fail("the monitor kept LATEST across FLUSH");
        // (e) CRC on, then SOFT_RESET
        r14_write(A_IF_CFG, 8'h01); bfm_crc_en = 1'b1;
        rd(A_CFG_GEN, v); expect8(v, 8'(n_apply), "CFG_GEN with CRC");
        rd(A_DROP_CNT, v); expect8(v, 8'(n_drop), "DROP_CNT with CRC");
        r14_cmd(CMD_SOFT_RESET); bfm_crc_en = 1'b0;
        repeat (400) @(posedge MCLK);
        rd(A_CFG_GEN, v);  expect8(v, 8'h00, "CFG_GEN after SOFT_RESET");
        rd(A_DROP_CNT, v); expect8(v, 8'h00, "DROP_CNT after SOFT_RESET");
        lat_expect("LATEST after SOFT_RESET");
        $display("tb_r15 (depth %0d): %0d checks, %0d failures, %0d SPI errors, %0d applies", FD, checks, errors,
                 spi_errors, n_apply);
        if (errors == 0 && spi_errors == 0) $display("PASS: tb_r15");
        else $display("FAIL: tb_r15");
        $finish;
    end
endmodule

`default_nettype wire
