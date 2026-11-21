// tb_a25_stop - audit round 25 (A): the earliest STOP (or any command) a host following requirements 5.4 rule (b)
// of round 24 (one CRC read of STATUS started >= 17 frames after the command's CS_N rise) can put after an APPLY_NR
// and after an APPLY, at 2 MHz with the specification's minimum CS_N timing; CRC on; 128 and 64 kHz.
// Measures the time from the command's tick (OFM change) to the next command's tick, sweeping the command's phase
// against the tick, and the sequencer's state at the STOP's tick after an APPLY.
`timescale 1ns / 1ps
`default_nettype none

module tb_a25_stop;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    localparam real TFRAME = 32.0 * TMCLK;
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

    // every command taken at a tick: time, code, state
    real    ack_t [0:15];
    integer ack_code [0:15];
    integer ack_state [0:15];
    integer nack = 0;
    always @(posedge MCLK) if (dut.u_seq.cmd_ack) begin
        ack_t[nack % 16] = $realtime; ack_code[nack % 16] = dut.u_seq.cmd_code; ack_state[nack % 16] = dut.u_seq.state;
        nack = nack + 1;
    end
    real t_afe_rise = 0.0;
    always @(posedge AFE_RST) t_afe_rise = $realtime;

    integer errors = 0;
    task automatic wait_state(input logic [3:0] s, input real tmax_ms);
        real t0;
        t0 = $realtime;
        while (dut.u_seq.state !== s && $realtime - t0 < tmax_ms * 1e6) @(posedge MCLK);
        if (dut.u_seq.state !== s) begin errors++; $display("ERROR: state %0d not reached", s); end
    endtask
    task automatic wait_tick_then(input real d);
        @(posedge dut.tick);
        #(d);
    endtask
    // the host's command check of rule (b) (round 24): the first read starts >= 17 frames after the command's CS_N rise
    task automatic host_cmd(input logic [7:0] code, output real t_cs);
        logic [7:0] st;
        r14_cmd(code);
        t_cs = $realtime - spi_tidle;
        while ($realtime < t_cs + 17.0 * TFRAME) #1;
        r14_read(7'h03, st);
        if (st[STATUS_CMD_PENDING_LSB] !== 1'b0) begin errors++; $display("ERROR: CMD_PENDING 1 at the rule-(b) read"); end
    endtask

    real    t_cs, g, gmin, gmax;
    integer k, rate, m, i0;
    logic [7:0] v;
    initial begin
        // the specification's minimum SPI timing at 2 MHz (spec 3.1)
        spi_high = 250.0; spi_low = 250.0; spi_tcss = 5.0 * TMCLK + 1.0; spi_tcsh = 3.0 * TMCLK + 1.0;
        spi_tidle = 4.0 * TMCLK + 1.0;
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;        // CRC on
        r14_write(7'h50, 8'd5); r14_write(7'h52, 8'd29);      // T_WARM 5 ms, T_REC minimum
        r14_write(7'h22, 8'h01); m = 64; r14_write(7'h21, m[7:0]);   // range 1, M 64
        for (rate = 1; rate >= 0; rate--) begin
            r14_write(7'h26, rate[7:0]);                       // CHOP_FAST
            if (rate == 1) begin
                r14_cmd(8'h11);                                 // START
            end else begin
                r14_cmd(8'h33);                                 // APPLY (the rate)
                while (dut.u_seq.state === ST_RUN) @(posedge MCLK);
            end
            wait_state(ST_RUN, 30.0);
            // APPLY_NR, then the next command as early as rule (b) allows; the command's phase swept over a tick period
            gmin = 1e9; gmax = 0.0;
            for (k = 0; k < 16; k++) begin
                m = m + ((k % 2) ? -1 : 1);
                r14_write(7'h21, m[7:0]);
                wait_tick_then(k * (rate ? 8.0 : 16.0) * TFRAME / 16.0 + 3.0);
                i0 = nack;
                host_cmd(8'h44, t_cs);                          // APPLY_NR
                r14_cmd(8'h55);                                 // FLUSH as the probe (taken at a tick, no state change)
                while (nack < i0 + 2) @(posedge MCLK);
                g = (ack_t[(i0 + 1) % 16] - ack_t[i0 % 16]) / 1000.0;
                if (g < gmin) gmin = g;
                if (g > gmax) gmax = g;
                #(20000.0);
            end
            $display("%0s kHz: APPLY_NR tick -> next command's tick, rule (b) host at 2 MHz: %0.2f .. %0.2f us",
                     rate ? "128" : "64", gmin, gmax);
            // one real STOP right after an APPLY_NR: AFE_RST's rise against the OFM change
            m = m + 1; r14_write(7'h21, m[7:0]);
            wait_tick_then((rate ? 7.5 : 15.0) * TFRAME);
            i0 = nack;
            host_cmd(8'h44, t_cs);
            r14_cmd(8'h22);                                     // STOP
            while (nack < i0 + 2) @(posedge MCLK);
            #(2.0 * TMCLK);
            $display("  STOP after APPLY_NR: AFE_RST rose %0.2f us after the APPLY_NR's tick (state at the STOP's tick %0d)",
                     (t_afe_rise - ack_t[i0 % 16]) / 1000.0, ack_state[(i0 + 1) % 16]);
            r14_cmd(8'h11);
            wait_state(ST_RUN, 30.0);
            // APPLY in RUN, then STOP as early as rule (b) allows: is the STOP taken in PRE?
            for (k = 0; k < 8; k++) begin
                wait_tick_then(k * (rate ? 8.0 : 16.0) * TFRAME / 8.0 + 3.0);
                i0 = nack;
                host_cmd(8'h33, t_cs);                          // APPLY
                r14_cmd(8'h22);                                 // STOP
                while (nack < i0 + 2) @(posedge MCLK);
                $display("  APPLY phase %0d/8: STOP taken %0.2f us after the APPLY's tick, in state %0d (7 = PRE)",
                         k, (ack_t[(i0 + 1) % 16] - ack_t[i0 % 16]) / 1000.0, ack_state[(i0 + 1) % 16]);
                r14_cmd(8'h11);
                wait_state(ST_RUN, 30.0);
            end
        end
        r14_read(7'h06, v);
        $display("ERR 0x%02h, SPI errors %0d, errors %0d", v, spi_errors, errors);
        $display(errors == 0 && spi_errors == 0 ? "PASS" : "FAIL");
        $finish;
    end
endmodule

`default_nettype wire
