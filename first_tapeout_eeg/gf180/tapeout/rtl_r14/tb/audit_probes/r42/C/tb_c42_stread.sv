// audit42 C probe: the data byte of a STATUS (0x03) read and of an ERR (0x06) read against the register of its load
// cycle (spec 3.2: "the value of the cycle that loads it into MISO").
// (1) STATUS: a FLUSH written right after a tick is taken two ticks on; a STATUS read started 0.5 .. 4 us before that
//     tick (the tick falls inside its header byte): the header has CMD_PENDING 1, the data byte must have 0.
// (2) ERR: an APPLY refused with CFG_ERR (range 1, M 200) at the tick two on; an ERR read whose data byte's load
//     cycle is aimed from 3 MCLK before CFG_ERR's edge to 3 MCLK after it in 1/4-MCLK steps.
`timescale 1ns / 1ps
`default_nettype none
module tb_c42_stread;
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
    logic [7:0] ld_status, ld_err; bit ld_got; real t_ld, t_cfg;
    always @(negedge CS_N) ld_got = 1'b0;
    always @(posedge MCLK)
        if (dut.u_spi.sclk_fall === 1'b1 && dut.u_spi.bit_cnt == 3'd0 && dut.u_spi.st == 4'd2 && !ld_got) begin
            ld_got = 1'b1; t_ld = $realtime;              // the load edge; the values of the cycle it ends
            ld_status = dut.u_regs.status_byte;
            ld_err = dut.u_regs.err;
        end
    always @(posedge dut.u_regs.err[ERR_CFG_ERR_LSB]) t_cfg = $realtime;
    integer nbad = 0, nst = 0, nhdr = 0, ne = 0, nb = 0, ns = 0, na = 0;
    initial begin
        logic [7:0] v;
        real t1, t0, lat, d;
        #(20 * TMCLK); RESET_N = 1'b1; #(50 * TMCLK);
        r14_write(7'h06, 8'hFF);
        t0 = $realtime; r14_read(7'h04, v); lat = t_ld - t0;          // a read's start to its data byte's load
        for (int k = 0; k < 8; k++) begin                               // (1)
            @(posedge dut.u_clkgen.tick); t1 = $realtime; #(200.0);
            spi_tidle = 100.0; r14_cmd(8'h55); spi_tidle = 600.0;      // FLUSH: taken at the tick 15.6 us on
            #(t1 + 15625.0 - 500.0 - 500.0 * k - $realtime);
            r14_read(7'h03, v);
            nst++;
            if (spi_status[STATUS_CMD_PENDING_LSB] === 1'b1 && v[STATUS_CMD_PENDING_LSB] === 1'b0) nhdr++;
            if (v !== ld_status) begin
                nbad++;
                if (nbad <= 6) $display("ERROR (1) k %0d: STATUS data byte 0x%02h (header 0x%02h); the register in its load cycle 0x%02h",
                                        k, v, spi_status, ld_status);
            end
            repeat (400) @(posedge MCLK);
        end
        r14_write(7'h20, 8'h00); r14_write(7'h21, 8'd200); r14_write(7'h22, 8'h01);   // range 1, M 200: CFG_ERR
        for (int j = -12; j <= 12; j++) begin                           // (2)
            r14_write(7'h06, 8'hFF);
            @(posedge dut.u_clkgen.tick); t1 = $realtime; #(200.0);
            spi_tidle = 100.0; r14_cmd(8'h33); spi_tidle = 600.0;      // APPLY, refused at the tick 15.6 us on
            // CFG_ERR is set at e25, one MCLK after the tick's rising edge: the load edge at e25 + 1 MCLK + j/4 MCLK
            #(t1 + 15625.0 + TMCLK + TMCLK + j * TMCLK / 4.0 - lat - $realtime);
            r14_read(7'h06, v);
            ne++;
            d = (t_cfg - (t_ld - TMCLK)) / TMCLK;                       // CFG_ERR's edge from the load cycle's start
            if (d < -0.5) nb++; else if (d < 0.5) ns++; else na++;
            if (v !== ld_err) begin
                nbad++;
                if (nbad <= 12) $display("ERROR (2) j %0d: ERR data byte 0x%02h; the register in its load cycle 0x%02h (CFG_ERR's edge %0.2f MCLK from the load cycle's start)",
                                         j, v, ld_err, d);
            end
            repeat (400) @(posedge MCLK);
        end
        $display("tb_c42_stread: (1) %0d STATUS reads, %0d with CMD_PENDING 1 in the header and 0 in the data byte; (2) %0d ERR reads, CFG_ERR's edge before / at the start of / after the load cycle %0d / %0d / %0d; %0d mismatches with the register of the load cycle; SPI errors %0d",
                 nst, nhdr, ne, nb, ns, na, nbad, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
