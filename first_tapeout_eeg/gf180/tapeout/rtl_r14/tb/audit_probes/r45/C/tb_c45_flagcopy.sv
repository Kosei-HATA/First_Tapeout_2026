// Audit 45, auditor C: the header STATUS of a status poll (a header-only read of 0x03) whose copy cycle (cs_start) is
// swept in 1/4-MCLK steps across the tick that refuses a pending APPLY with CFG_ERR (IDLE, 64 kHz, range 1, M 200),
// with ALERT_MASK 0x20 (CFG_ERR alone) and ALERT_MASK_D 0. Prints CMD_PENDING and ALERT of every copy and counts the
// copies that show the command taken (CMD_PENDING 0) with no alert (ALERT 0) although it was refused.
`timescale 1ns / 1ps
`default_nettype none
module tb_c45_flagcopy;
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

    real t_cs = 0.0, t_ack = 0.0, t_err = 0.0;
    logic err_q = 1'b0;
    always @(posedge MCLK) begin
        if (dut.u_spi.cs_start) t_cs = $realtime;          // the copy's edge: the end of the cs_start cycle
        if (dut.cmd_ack) t_ack = $realtime;                // the edge that ends the ack cycle (e25)
    end
    always @(negedge MCLK) begin
        if (dut.u_regs.err[ERR_CFG_ERR_LSB] === 1'b1 && err_q === 1'b0) t_err = $realtime - TMCLK / 2.0;
        err_q = dut.u_regs.err[ERR_CFG_ERR_LSB];
    end

    integer bad = 0, n00 = 0, n10 = 0, n01 = 0, n11 = 0;
    real lat, d_ack, t0, tgt;
    logic [7:0] v;
    initial begin
        #(10 * TMCLK); RESET_N = 1'b1; #(40 * TMCLK);
        r14_write(7'h26, 8'h00);                            // CHOP_FAST 0
        r14_cmd(8'h33);                                     // APPLY in IDLE: 64 kHz
        #(40000.0);
        r14_write(7'h08, 8'h20);                            // ALERT_MASK: CFG_ERR alone
        r14_write(7'h09, 8'h00);
        r14_write(7'h22, 8'h01);                            // range 1
        r14_write(7'h21, 8'd200);                           // M 200 > 127: the APPLY is refused
        r14_write(7'h06, 8'hFF);
        // calibration: a header-only read's start to its copy edge, and a tick to the ack edge of the APPLY written
        t0 = $realtime; spi_tx[0] = 8'h83; spi_xfer(1, 0); lat = t_cs - t0;
        @(posedge dut.u_clkgen.tick); t0 = $realtime;
        r14_cmd(8'h33);
        repeat (700) @(posedge MCLK);
        d_ack = t_ack - t0;
        $display("calibration: copy %0.1f ns after the read's start; ack edge %0.1f ns after the tick; CFG_ERR set %0.2f MCLK after the ack edge",
                 lat, d_ack, (t_err - t_ack) / TMCLK);
        r14_write(7'h06, 8'hFF);
        for (int k = -12; k <= 12; k++) begin
            @(posedge dut.u_clkgen.tick); t0 = $realtime;
            r14_cmd(8'h33);
            tgt = t0 + d_ack + k * TMCLK / 4.0 - lat;
            if (tgt > $realtime) #(tgt - $realtime);
            else begin $display("ERROR k %0d: due %0.1f ns ago", k, $realtime - tgt); bad = bad + 1; end
            spi_tx[0] = 8'h83; spi_xfer(1, 0);
            v = spi_rx[0];
            $display("k %3d: copy %5.2f MCLK from the ack edge: STATUS 0x%02h CMD_PENDING %b ALERT %b", k,
                     (t_cs - t_ack) / TMCLK, v, v[STATUS_CMD_PENDING_LSB], v[STATUS_ALERT_LSB]);
            case ({v[STATUS_CMD_PENDING_LSB], v[STATUS_ALERT_LSB]})
                2'b00: n00 = n00 + 1;
                2'b01: n01 = n01 + 1;
                2'b10: n10 = n10 + 1;
                default: n11 = n11 + 1;
            endcase
            repeat (700) @(posedge MCLK);
            r14_read(7'h06, v);
            if (v !== 8'h20) begin $display("ERROR k %0d: ERR 0x%02h, expected CFG_ERR", k, v); bad = bad + 1; end
            r14_write(7'h06, 8'hFF);
            if (dut.seq_state !== 4'd0) begin $display("ERROR: left IDLE"); bad = bad + 1; end
        end
        $display("tb_c45_flagcopy: STATUS copies (CMD_PENDING, ALERT): (1,0) %0d, (0,1) %0d, (0,0) %0d, (1,1) %0d; errors %0d, SPI errors %0d",
                 n10, n01, n00, n11, bad, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
