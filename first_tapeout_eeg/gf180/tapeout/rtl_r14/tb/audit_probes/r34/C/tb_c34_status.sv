// tb_c34_status (audit 34, C): a flag set at the edge that starts a store's cycle (frame cycle 8). Spec 3.4: the
// sample's ERR = ALERT at the store. The sequencer is put in RUN by a deposit, RESET_FLAG cleared by a deposit, and
// FRAME_ERR's pulse is forced in the cycle before the store (step 3), so ALERT rises at the store's own edge.
`timescale 1ns / 1ps
`default_nettype none
module tb_c34_status;
    logic MCLK = 0, RESET_N = 0, SCLK = 0, CS_N = 1, MOSI = 0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(1000.0 / 32.768 / 2.0) MCLK = ~MCLK;
    integer n = 0;
    logic [7:0] st;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1;
        while (n < 3) begin @(posedge MCLK); if (dut.cic_stb) n++; end      // the CIC valid from the third output
        @(negedge MCLK);
        dut.u_seq.state = 4'd6;                                           // RUN (deposit)
        dut.u_regs.err  = 8'h00;                                          // RESET_FLAG cleared (deposit)
        @(posedge dut.cic_stb);                                           // one store in RUN, then the next one:
        @(negedge MCLK);
        while (dut.u_cic.step[3] !== 1'b1) @(negedge MCLK);              // cycle 7 of the next output's frame
        force dut.u_spi.frame_err = 1'b1;                                 // FRAME_ERR set at the edge of cycle 8
        @(negedge MCLK);
        release dut.u_spi.frame_err;
        if (dut.cic_stb !== 1'b1 || dut.push_ok !== 1'b1 || dut.alert !== 1'b1)
            $display("SETUP: cic_stb %b push_ok %b alert %b in the store cycle", dut.cic_stb, dut.push_ok, dut.alert);
        @(negedge MCLK);
        st = dut.u_fifo.mem[dut.u_fifo.wr_ptr - 3'd1][47:40];
        $display("store at SEQ %0d with ALERT %b (ERR 0x%02h): stored status 0x%02h, ERR bit %b (spec 3.4: ALERT at the store, 1)",
                 dut.u_fifo.mem[dut.u_fifo.wr_ptr - 3'd1][39:24], dut.alert, dut.u_regs.err, st, st[3]);
        $finish;
    end
endmodule
`default_nettype wire
