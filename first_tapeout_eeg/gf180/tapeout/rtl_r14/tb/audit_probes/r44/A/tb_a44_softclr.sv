// audit 44 A probe: SEQ-13 (round 41) says a SOFT_RESET committed 2 MCLK cycles before ALIGN's output time also
// cancels the CIC clear (the control reset returns the sequencer to IDLE and drops cic_arm), as do ones committed 3..7
// cycles before; one committed in the output-time cycle (cycle 8) comes after the clear. Zero-delay RTL check: for each
// commit cycle c in 1..8 of the output frame (soft_req forced for one cycle, as tb_top_r14's R does), from a fresh
// START into ALIGN, the clear taken at the output (eeg_cic3 step 3 with arm) and the state afterwards.
`timescale 1ns / 1ps
`default_nettype none
module tb_a44_softclr;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd12 + 5'($urandom % 8);

    integer errors = 0;
    logic   clr_taken, clr_seen;
    always @(posedge MCLK) if (dut.u_cic.step[3]) begin clr_seen = 1'b1; clr_taken = dut.u_cic.arm; end

    initial begin : main
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        for (int c = 1; c <= 9; c++) begin
            r14_cmd(8'h11);                                      // START (T_ELEC 0): WARMUP, RECOVER, ALIGN
            wait (dut.seq_state == ST_ALIGN);
            // the output frame: the CIC's step 3 is in cycle 7 of frame 1024 n + 1023; commit in cycle c of that frame
            wait (dut.u_cic.dcnt == 10'd1023 && dut.cycle == 5'd0);
            clr_seen = 1'b0; clr_taken = 1'bx;
            @(negedge MCLK);
            while (dut.cycle != 5'(c)) @(negedge MCLK);        // sampled mid-cycle: inside cycle c (no edge race)
            force dut.soft_req = 1'b1;
            @(negedge MCLK);
            release dut.soft_req;
            while (dut.cycle != 5'd10) @(posedge MCLK);
            if (clr_seen !== 1'b1) begin $display("ERROR: no output time seen"); errors++; end
            repeat (40) @(posedge MCLK);
            $display("SOFT_RESET committed in cycle %0d of ALIGN's output frame: clear %s, state %0d, AFE_RST %b, CIC nstb %0d, i1 %s",
                     c, clr_taken ? "taken" : "cancelled", dut.seq_state, AFE_RST, dut.u_cic.nstb,
                     (dut.u_cic.i1 == 0) ? "0" : "not 0");
            if ((c <= 7) == (clr_taken === 1'b1)) begin
                $display("ERROR: commit in cycle %0d: clear %s (SEQ-13: cycles up to 7 cancel it, 8 comes after it)", c, clr_taken ? "taken" : "cancelled");
                errors++;
            end
            if (dut.seq_state != ST_IDLE || AFE_RST !== 1'b1) begin $display("ERROR: not IDLE with AFE_RST 1 after the SOFT_RESET"); errors++; end
            #(3000.0);
        end
        $display("tb_a44_softclr done: errors %0d, SPI errors %0d", errors, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
