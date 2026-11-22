// tb_c33_fillclr - audit round 33, auditor C: an APPLY_NR (T_ELEC 0) or an APPLY issued in FILL, swept over FILL.
// The specification clears the CIC at ALIGN's output time (fsm_spec ALIGN/OUT: cic_clear) and FILL stores the third
// output after it (FILL/OUT [valid]); so the first sample stored after the command must be ALIGN's output + 3, and
// the CIC must actually be cleared at ALIGN's output. Printed per trial; counts of violations at the end.
`timescale 1ns / 1ps
`default_nettype none
module tb_c33_fillclr;
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

    integer fcodes, ncodes, cidx = 0;
    logic [4:0] codes [0:262143];
    initial begin
        fcodes = $fopen("build/top_r14.codes", "r");
        ncodes = 0;
        while (!$feof(fcodes) && ncodes < 262144) if ($fscanf(fcodes, "%d\n", codes[ncodes]) == 1) ncodes = ncodes + 1;
        $fclose(fcodes);
    end
    always @(posedge MCLK) if (dut.cycle == 5'd1 && RESET_N) begin CODE <= codes[cidx % ncodes]; cidx <= cidx + 1; end

    integer align_seq = -1, first_store = -1;
    bit     align_cleared = 1'b0, align_valid_before = 1'b0, armed_trial = 1'b0;
    always @(negedge MCLK) begin
        if (armed_trial && dut.cic_stb === 1'b1 && dut.seq_state === 4'd4) begin   // ALIGN's output time
            align_seq     = dut.seq_cnt;
            align_cleared = (dut.u_cic.nstb == 0) && (dut.u_cic.i1 == 0) && (dut.u_cic.i3 == 0);
            align_valid_before = dut.u_cic.dout_valid;
        end
        if (armed_trial && dut.push_ok === 1'b1 && first_store < 0 && align_seq >= 0) first_store = dut.seq_cnt;
    end

    task automatic wait_state(input logic [3:0] s, input real timeout_us);
        real t0;
        t0 = $realtime;
        while (dut.seq_state !== s && ($realtime - t0) < timeout_us * 1000.0) @(posedge MCLK);
        if (dut.seq_state !== s) begin $display("TIMEOUT waiting for state %0d (now %0d)", s, dut.seq_state); $finish; end
    endtask

    integer nviol = 0, ntr = 0, nskip = 0;
    initial begin
        logic [7:0] m;
        m = 8'd0;
        repeat (10) @(posedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(posedge MCLK);
        r14_write(7'h06, 8'hFF);
        r14_cmd(8'h11);                              // START (range 0, T_ELEC 0)
        wait_state(4'd6, 12000.0);
        for (int cmd = 0; cmd < 2; cmd++) begin       // 0: APPLY_NR (T_ELEC 0) in FILL, 1: APPLY in FILL
            for (int k = 0; k < 9; k++) begin
                real d;
                d = 40.0 + 330.0 * k;                    // us after FILL's entry
                r14_cmd(8'h33);                          // APPLY in RUN: back to FILL through ALIGN (valid output)
                wait_state(4'd5, 3000.0);
                #(d * 1000.0);
                if (dut.seq_state !== 4'd5) begin nskip++; wait_state(4'd6, 5000.0); continue; end
                align_seq = -1; first_store = -1; armed_trial = 1'b1;
                if (cmd == 0) begin
                    m = m ^ 8'd1;
                    r14_write(7'h21, m);                 // M 0 <-> 1: one step (range 0)
                    r14_cmd(8'h44);
                end else begin
                    r14_cmd(8'h33);
                end
                wait_state(4'd4, 1000.0);                // ALIGN
                wait_state(4'd6, 6000.0);                // RUN
                repeat (40) @(posedge MCLK);
                armed_trial = 1'b0;
                ntr++;
                $display("%s in FILL %6.1f us after its entry: ALIGN's output SEQ %0d (CIC output valid before it %0d), CIC cleared there %0d, first stored SEQ %0d (specification %0d) %s",
                         cmd == 0 ? "APPLY_NR" : "APPLY   ", d, align_seq, align_valid_before, align_cleared, first_store,
                         align_seq + 3, (first_store == align_seq + 3 && align_cleared) ? "ok" : "VIOLATION");
                if (!(first_store == align_seq + 3 && align_cleared)) nviol++;
            end
        end
        $display("tb_c33_fillclr: %0d trials (%0d skipped: FILL already over), %0d violations, SPI errors %0d", ntr, nskip, nviol, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
