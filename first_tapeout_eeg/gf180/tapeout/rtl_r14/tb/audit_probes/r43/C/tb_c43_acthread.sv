// audit43 C probe: the data byte of an OFF_M_H active-copy (0x30) read against the register of its load cycle (spec 3.2),
// at the tick of an APPLY_NR in IDLE that moves M between 255 and 256 (range 3): the load cycle aimed from 3 MCLK
// before the copy's edge (e25) to 3 MCLK after it in 1/4-MCLK steps (tb_top_r14's AM sweeps OFF_M_L's copy only)
`timescale 1ns / 1ps
`default_nettype none
module tb_c43_acthread;
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
    logic [7:0] ld_v; bit ld_got; real t_ld, t_chg;
    always @(negedge CS_N) ld_got = 1'b0;
    always @(posedge MCLK)
        if (dut.u_spi.sclk_fall === 1'b1 && dut.u_spi.bit_cnt == 3'd0 && dut.u_spi.st == 4'd2 && !ld_got) begin
            ld_got = 1'b1; t_ld = $realtime;
            ld_v = {6'd0, dut.u_regs.a_m[9:8]};
        end
    always @(dut.u_regs.a_m[9:8]) t_chg = $realtime;
    integer nbad = 0, n = 0, nb = 0, ns = 0, na = 0;
    initial begin
        logic [7:0] v;
        real t1, t0, lat, d;
        #(20 * TMCLK); RESET_N = 1'b1; #(50 * TMCLK);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h22, 8'h03);                                  // range 3 (M up to 511)
        r14_write(7'h20, 8'h00); r14_write(7'h21, 8'hFF);         // M 255
        r14_cmd(8'h44); repeat (800) @(posedge MCLK);             // applied in IDLE
        t0 = $realtime; r14_read(7'h30, v); lat = t_ld - t0;
        for (int j = -12; j <= 12; j++) begin
            if (j % 2 == 0) begin r14_write(7'h20, 8'h01); r14_write(7'h21, 8'h00); end     // M 256
            else            begin r14_write(7'h20, 8'h00); r14_write(7'h21, 8'hFF); end     // M 255
            @(posedge dut.u_clkgen.tick); t1 = $realtime; #(200.0);
            spi_tidle = 100.0; r14_cmd(8'h44); spi_tidle = 600.0;      // APPLY_NR, taken at the tick 15.6 us on
            #(t1 + 15625.0 + TMCLK + TMCLK + j * TMCLK / 4.0 - lat - $realtime);
            r14_read(7'h30, v);
            n++;
            d = (t_chg - (t_ld - TMCLK)) / TMCLK;
            if (d < -0.5) nb++; else if (d < 0.5) ns++; else na++;
            if (v !== ld_v) begin
                nbad++;
                if (nbad <= 6) $display("ERROR j %0d: OFF_M_H active copy read 0x%02h; the register in its load cycle 0x%02h (the copy's edge %0.2f MCLK from the load cycle's start)",
                                        j, v, ld_v, d);
            end
            repeat (800) @(posedge MCLK);
        end
        $display("tb_c43_acthread: %0d reads of 0x30, the copy's edge before / at the start of / after the load cycle %0d / %0d / %0d; %0d mismatches with the register of the load cycle; SPI errors %0d",
                 n, nb, ns, na, nbad, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
