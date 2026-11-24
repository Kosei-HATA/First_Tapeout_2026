// tb_b42_lvlwin2 - audit round 42, auditor B: step 5 (ii)'s window method (the FIFO_LEVEL read "w before" the
// predicted output time) on the RTL. One chip, CRC on, level mode, RUN, SCLK 1 MHz. After a read-out to the empty word,
// a CRC FIFO_LEVEL read is started so that its CS_N falls before the next store; the read's CS_N fall, its data byte's
// load (spec 3.2: the synchronized SCLK fall after the header) and the store are timed. Which instant decides the value?
`timescale 1ns / 1ps
`default_nettype none
module tb_b42_lvlwin2;
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
    real t_store, t_load, t_drdy_fall;
    always @(posedge MCLK) if (dut.u_fifo.push_ok) t_store = $realtime;        // the store cycle (its end edge next)
    always @(posedge MCLK) if (dut.u_spi.sclk_fall && dut.u_spi.bit_cnt == 3'd0 && dut.u_spi.st == 4'd2) t_load = $realtime;
    always @(negedge DRDY_N) t_drdy_fall = $realtime;
    logic [7:0] v, sst; logic [15:0] sq; logic [23:0] dt; bit ok;
    task automatic readout();
        forever begin
            r14_sample(sst, sq, dt, ok);
            if (ok && !sst[SMP_VALID_LSB] && spi_status[STATUS_DATA_LSB] == 1'b0) break;
        end
    endtask
    initial begin #(400e6); $display("FAIL: watchdog"); $finish; end
    initial begin
        real t_next, t_cs, lead;
        integer n;
        spi_high = 500.0; spi_low = 500.0;                                  // 1 MHz
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h09, 8'h00);
        r14_write(7'h52, 8'd29);
        r14_write(7'h10, 8'h11);
        while (dut.seq_state !== ST_RUN) @(posedge MCLK);
        readout();
        // lead = time from the read's CS_N fall to the next store (us), 1 MHz: header 8 us + tcss 0.3 us
        for (n = 0; n < 20; n++) begin
            @(negedge DRDY_N);                                              // an output time (level mode, FIFO empty)
            readout();
            t_next = t_drdy_fall + 1.0e6;                                   // the predicted next DRDY_N fall
            lead = 8000.0 - n * TMCLK / 4.0;
            #(t_next - $realtime - lead);
            t_cs = $realtime;
            r14_read(7'h05, v);
            readout();                                                      // empty again: DRDY_N falls at the next store
            $display("CS_N fall %6.3f us before the predicted DRDY_N fall: header DATA %0d, FIFO_LEVEL %0d (CRC %s); data byte loaded %6.1f ns before the predicted DRDY_N fall; store edge %6.1f ns before it",
                     (t_next - t_cs) / 1000.0, spi_status[STATUS_DATA_LSB], v, spi_errors == 0 ? "ok" : "BAD",
                     t_next - t_load, t_next - t_store);
        end
        $display("tb_b42_lvlwin2 done: %0d SPI errors", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
