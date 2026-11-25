// audit round 46, auditor C: the SPI's documented instants measured at the pins (spec 3.2: a write's commit, FRAME_ERR
// and CRC_ERR at the edge 3-4 MCLK after CS_N's pad rise; a read header's undefined-address ADDR_ERR at the edge 2 MCLK
// after the cycle that took the header's 8th SCLK rise; spec 3.3: DRDY_N (level) back high at most 5 MCLK after the
// CS_N rise of the read that emptied the FIFO). The CS_N rise is swept over one MCLK in 1/8 steps; the flag's change
// is taken from eeg_regs' err (a probe; the bench is not part of the suite)
`timescale 1ns / 1ps
`default_nettype none
module tb_c46_instants;
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
    real t_rise, t_flag, t_hdr8, t_we;
    real mn [0:4], mx [0:4];
    initial for (int i = 0; i < 5; i++) begin mn[i] = 1e9; mx[i] = -1e9; end
    always @(posedge CS_N) t_rise = $realtime;
    always @(posedge MCLK) if (dut.reg_we === 1'b1) t_we = $realtime;
    task automatic note(input int k, input real v);
        if (v < mn[k]) mn[k] = v;
        if (v > mx[k]) mx[k] = v;
    endtask
    // a write frame of nbytes (+extra bits), CS_N rising at an offset off (ns) after an MCLK rising edge
    task automatic frame_at(input integer nbytes, input integer extra, input real off);
        @(posedge MCLK); #(off);
        spi_xfer(nbytes, extra);
    endtask
    initial begin
        logic [7:0] e;
        repeat (5) @(posedge MCLK); RESET_N = 1'b1; repeat (20) @(posedge MCLK);
        r14_write(7'h06, 8'hFF);                         // RESET_FLAG cleared
        for (int p = 0; p < 8; p++) begin
            real off; off = p * TMCLK / 8.0;
            // (0) a commit: CPF_TRIM written, its shadow changes at the commit's edge
            spi_tx[0] = 8'h24; spi_tx[1] = 8'(p + 1); spi_tidle = 600.0;
            fork
                frame_at(2, 0, off);
                begin @(dut.u_regs.s_cpf); t_flag = $realtime; end
            join
            note(0, (t_flag - t_rise) / TMCLK);
            // (1) FRAME_ERR: a header-only write
            spi_tx[0] = 8'h24;
            fork
                frame_at(1, 0, off);
                begin @(posedge dut.u_regs.err[ERR_FRAME_ERR_LSB]); t_flag = $realtime; end
            join
            note(1, (t_flag - t_rise) / TMCLK);
            r14_write(7'h06, 8'hFF);
            // (2) CRC_ERR: CRC on, a write with a wrong CRC
            r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
            spi_tx[0] = 8'h24; spi_tx[1] = 8'h03; spi_tx[2] = 8'h00;
            fork
                frame_at(3, 0, off);
                begin @(posedge dut.u_regs.err[ERR_CRC_ERR_LSB]); t_flag = $realtime; end
            join
            note(2, (t_flag - t_rise) / TMCLK);
            r14_write(7'h06, 8'hFF);
            r14_write(7'h55, 8'h00); bfm_crc_en = 1'b0;
            r14_write(7'h06, 8'hFF);
            // (3) a read header's ADDR_ERR (undefined 0x7F), from the 8th SCLK rise at the pin
            spi_tx[0] = 8'hFF; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
            fork
                frame_at(3, 0, off);
                begin @(posedge SCLK); repeat (7) @(posedge SCLK); t_hdr8 = $realtime;
                      @(posedge dut.u_regs.err[ERR_ADDR_ERR_LSB]); t_flag = $realtime; end
            join
            note(3, (t_flag - t_hdr8) / TMCLK);
            r14_write(7'h06, 8'hFF);
            // (4) a sample read's copy of the FIFO head (smp_snap's cycle), from the 8th SCLK rise at the pin
            spi_tx[0] = 8'hC0; for (int i = 1; i < 8; i++) spi_tx[i] = 8'h00;
            fork
                frame_at(8, 0, off);
                begin @(posedge SCLK); repeat (7) @(posedge SCLK); t_hdr8 = $realtime;
                      @(posedge dut.smp_snap); t_flag = $realtime; end
            join
            note(4, (t_flag - t_hdr8) / TMCLK);
        end
        $display("commit: CS_N pad rise -> shadow change %0.2f..%0.2f MCLK (spec 3.2: 3..4)", mn[0], mx[0]);
        $display("FRAME_ERR: CS_N pad rise -> ERR bit %0.2f..%0.2f MCLK (spec 3.2: 3..4)", mn[1], mx[1]);
        $display("CRC_ERR: CS_N pad rise -> ERR bit %0.2f..%0.2f MCLK (spec 3.2: 3..4)", mn[2], mx[2]);
        $display("read header ADDR_ERR: 8th SCLK pad rise -> ERR bit %0.2f..%0.2f MCLK", mn[3], mx[3]);
        $display("sample copy (smp_snap rises): 8th SCLK pad rise -> %0.2f..%0.2f MCLK", mn[4], mx[4]);
        $display("probe done (spi errors %0d)", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
