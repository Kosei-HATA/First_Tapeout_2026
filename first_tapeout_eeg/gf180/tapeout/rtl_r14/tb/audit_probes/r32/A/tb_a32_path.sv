// tb_a32_path - audit round 32 (A) probe: the states a host polling STATE (0x04, CRC on, 2 MHz) sees while it waits
// for RUN after START (step 5) and after an APPLY in RUN (step 7's search), and how long each wait lasts, with the
// default timers and with T_ELEC 2 ms. Every poll's value is printed when it differs from the previous one.
`timescale 1ns / 1ps
`default_nettype none
module tb_a32_path;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd13 + 5'($urandom % 6);

    // poll STATE until RUN (10 us between polls); print each new value and the time since t0
    task automatic poll_to_run(input string what, input real t0);
        logic [7:0] v, last;
        integer n;
        last = 8'hFF; n = 0;
        do begin
            r14_read(7'h04, v);
            if (v !== last) $display("  %s: STATE %0d at %8.1f us", what, v, ($realtime - t0) / 1000.0);
            last = v; n = n + 1;
            #10000.0;
        end while (v !== 8'd6 && n < 20000);
        $display("  %s: RUN after %0.1f us (%0d polls)", what, ($realtime - t0) / 1000.0, n);
    endtask

    real t0;
    integer k;
    initial begin
        repeat (5) @(posedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(posedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;     // CRC on
        r14_write(7'h06, 8'hFF);
        r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd40);
        for (k = 0; k < 2; k++) begin
            if (k == 1) begin
                r14_cmd(8'h22); #20000.0;                // STOP
                r14_write(7'h51, 8'd2);                  // T_ELEC 2 ms
            end
            t0 = $realtime; r14_cmd(8'h11);              // START
            $display("START (T_ELEC %0d ms):", dut.u_regs.r_te);
            poll_to_run("after START", t0);
            #2000000.0;
            t0 = $realtime; r14_cmd(8'h33);              // APPLY in RUN (step 7's search)
            $display("APPLY in RUN (T_ELEC %0d ms):", dut.u_regs.r_te);
            poll_to_run("after APPLY", t0);
        end
        $display("SPI errors: %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
