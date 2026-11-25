// Audit 45, auditor C: ERR's W1C of CFG_ERR whose commit cycle is swept in 1/4-MCLK steps across the tick that refuses
// a pending APPLY with CFG_ERR (IDLE, 64 kHz, range 1, M 200; legal 2 MHz SPI). FLG-02: a set event in the cycle of
// its clear wins, so a W1C committed in the acknowledge cycle leaves CFG_ERR and one committed after it clears it.
`timescale 1ns / 1ps
`default_nettype none
module tb_c45_flagw1c;
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

    real t_ack = 0.0, t_we = 0.0;
    always @(posedge MCLK) begin
        if (dut.cmd_ack) t_ack = $realtime;               // the edge that ends the acknowledge cycle
        if (dut.reg_we)  t_we  = $realtime;               // the edge that ends a write's commit cycle
    end
    integer n_kept = 0, n_clr = 0, bad = 0;
    real lat, t0, tgt;
    logic [7:0] v;
    initial begin
        #(10 * TMCLK); RESET_N = 1'b1; #(40 * TMCLK);
        r14_write(7'h26, 8'h00);                            // CHOP_FAST 0
        r14_cmd(8'h33);                                     // APPLY in IDLE: 64 kHz
        #(40000.0);
        r14_write(7'h22, 8'h01);                            // range 1
        r14_write(7'h21, 8'd200);                           // M 200 > 127: the APPLYs are refused
        r14_write(7'h06, 8'hFF);
        spi_tidle = 4.0 * TMCLK + 0.3;
        t0 = $realtime; r14_write(7'h06, 8'h00); lat = t_we - t0;   // a write's start to its commit edge
        for (int k = -12; k <= 12; k++) begin
            @(posedge dut.u_clkgen.tick); t0 = $realtime;
            #(512.0 * TMCLK - 2000.0);                      // the APPLY commits about 6.4 us after the next tick
            r14_cmd(8'h33);                                 // taken (refused) at the tick after that: t0 + 1024 MCLK
            tgt = t0 + 1025.0 * TMCLK + k * TMCLK / 4.0 - lat;
            if (tgt > $realtime) #(tgt - $realtime);
            else begin $display("ERROR k %0d: due %0.1f ns ago", k, $realtime - tgt); bad = bad + 1; end
            r14_write(7'h06, 8'h20);                        // CFG_ERR's W1C
            repeat (100) @(posedge MCLK);
            r14_read(7'h06, v);
            $display("k %3d: W1C committed %5.2f MCLK from the ack edge: ERR 0x%02h afterwards", k,
                     (t_we - t_ack) / TMCLK, v);
            if (v[ERR_CFG_ERR_LSB]) n_kept = n_kept + 1; else n_clr = n_clr + 1;
            r14_write(7'h06, 8'hFF);
            if (dut.seq_state !== 4'd0) begin $display("ERROR: left IDLE"); bad = bad + 1; end
        end
        $display("tb_c45_flagw1c: CFG_ERR kept by the W1C %0d times, cleared %0d times; errors %0d, SPI errors %0d",
                 n_kept, n_clr, bad, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
