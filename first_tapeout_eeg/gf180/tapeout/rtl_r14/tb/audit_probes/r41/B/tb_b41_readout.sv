// audit round 41, auditor B: what one read-out costs in pulse and in level mode (step 5's duty, step 6's stop rule)
`timescale 1ns / 1ps
`default_nettype none
module tb_b41_readout;
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
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(`DEPTH)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"

    integer n_store = 0, n_fall = 0;
    always @(posedge MCLK) if (dut.push_ok) n_store = n_store + 1;
    always @(negedge DRDY_N) n_fall = n_fall + 1;

    logic [7:0] ss; logic [15:0] sq; logic [23:0] dd; bit ok;
    real t0;
    // step 6's stop rule: a CRC-valid empty word whose header STATUS has the fixed bits and DATA = 0
    task automatic readout_empty(output integer nvalid, output integer nfr, output real dt);
        nvalid = 0; nfr = 0; t0 = $realtime;
        forever begin
            r14_sample(ss, sq, dd, ok); nfr = nfr + 1;
            if (ok && ss[SMP_VALID_LSB]) nvalid = nvalid + 1;
            if (ok && !ss[SMP_VALID_LSB] && spi_status[7:6] == 2'b10 && !spi_status[STATUS_DATA_LSB]) break;
            if (nfr > 20) break;
        end
        dt = $realtime - t0;
    endtask
    // level mode, step 5's duty: stop once DRDY_N is High (no empty word)
    task automatic readout_level(output integer nvalid, output integer nfr, output real dt);
        nvalid = 0; nfr = 0; t0 = $realtime;
        while (DRDY_N === 1'b0 && nfr <= 20) begin
            r14_sample(ss, sq, dd, ok); nfr = nfr + 1;
            if (ok && ss[SMP_VALID_LSB]) nvalid = nvalid + 1;
        end
        dt = $realtime - t0;
    endtask
    task automatic wait_outputs(input integer k);
        integer s0;
        s0 = dut.seq_cnt;
        while (16'(dut.seq_cnt - s0) < k) @(posedge MCLK);
        repeat (40) @(posedge MCLK);                   // past the store's DRDY_N edge
    endtask

    integer nv, nf;
    real dt;
    logic [7:0] v;
    initial begin
        // the round-39 frame times of the host procedure: 1 MHz, tcss 1 us, tcsh 0.5 us, 1 us between frames
        spi_high = 500.0; spi_low = 500.0; spi_tcss = 1000.0; spi_tcsh = 500.0; spi_tidle = 1000.0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h03);                       // step 3: CRC on, DRDY_N pulse mode (CRC-off frame)
        bfm_crc_en = 1'b1;
        r14_read(7'h55, v);
        $display("IF_CFG 0x%02h", v);
        r14_write(7'h52, 8'd29);
        r14_cmd(8'h11);                                // START
        while (dut.seq_state !== ST_RUN) @(posedge MCLK);
        wait_outputs(2);
        readout_empty(nv, nf, dt);
        $display("pulse: drained: %0d valid in %0d frames", nv, nf);
        // one 8-byte frame alone
        t0 = $realtime; r14_sample(ss, sq, dd, ok);
        $display("one 8-byte frame (T8) at 1 MHz: %0.2f us", ($realtime - t0) / 1000.0);
        t0 = $realtime; r14_read(7'h05, v);
        $display("one 3-byte read (T3) at 1 MHz: %0.2f us", ($realtime - t0) / 1000.0);
        for (int k = 1; k <= `DEPTH - 1; k++) begin
            readout_empty(nv, nf, dt);                 // empty first
            wait_outputs(k);
            readout_empty(nv, nf, dt);
            $display("pulse: deferred %0d outputs: %0d valid + empty = %0d frames, %0.1f us (%0.1f us per ms)",
                     k, nv, nf, dt / 1000.0, dt / 1000.0 / k);
        end
        r14_write(7'h55, 8'h01);                       // level mode, CRC on
        r14_read(7'h55, v);
        $display("IF_CFG 0x%02h", v);
        for (int k = 1; k <= `DEPTH - 1; k++) begin
            readout_empty(nv, nf, dt);
            wait_outputs(k);
            readout_level(nv, nf, dt);
            $display("level: deferred %0d outputs: %0d valid in %0d frames (stop on DRDY_N High), %0.1f us (%0.1f us per ms)",
                     k, nv, nf, dt / 1000.0, dt / 1000.0 / k);
        end
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
    initial begin #(200.0e6); $display("FAIL: watchdog"); $finish; end
endmodule
`default_nettype wire
