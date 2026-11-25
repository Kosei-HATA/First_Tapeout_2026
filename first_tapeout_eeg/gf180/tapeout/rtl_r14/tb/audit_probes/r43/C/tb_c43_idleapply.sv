// audit43 C: samples left in the FIFO after STOP across an APPLY and an APPLY_NR in IDLE (spec 2.3: "IDLE と WARMUP の
// APPLY はパルスなしで、FIFO を空にしない（STOP のあとに FIFO に残ったサンプルは、次の START まで読める）")
`timescale 1ns / 1ps
`default_nettype none
module tb_c43_idleapply;
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
    always @(posedge MCLK) if (CMP_STROBE) CODE <= 5'd14 + ($random % 4);
    `include "spi_bfm_r14.svh"
    logic [7:0] v, st; logic [15:0] sq; logic [23:0] d; bit ok;
    integer lvl0, lvl1, lvl2, nvalid;
    initial begin
        #(1000.0); RESET_N = 1'b1; #(2000.0);
        r14_cmd(8'h11);                                           // START with the defaults
        wait (dut.seq_state == 4'd6);
        wait (dut.fifo_level == 4'd3);                            // three samples stored, none read
        r14_cmd(8'h22);                                           // STOP: IDLE, the samples kept
        wait (dut.seq_state == 4'd0);
        r14_read(7'h05, v); lvl0 = v;
        r14_write(7'h24, 8'h05);                                  // CPF_TRIM shadow
        r14_cmd(8'h33);                                           // APPLY in IDLE (no pulse)
        #(20000.0);
        r14_read(7'h05, v); lvl1 = v;
        r14_write(7'h21, 8'h01);                                  // M 0 -> 1 (range 0)
        r14_cmd(8'h44);                                           // APPLY_NR in IDLE
        #(20000.0);
        r14_read(7'h05, v); lvl2 = v;
        r14_read(7'h06, v);
        nvalid = 0;
        for (int i = 0; i < 4; i++) begin
            r14_sample(st, sq, d, ok);
            if (ok && st[7]) nvalid++;
            $display("  sample %0d: status 0x%02h SEQ %0d CRC ok %0d", i, st, sq, ok);
        end
        $display("c43 idle apply: FIFO_LEVEL after STOP %0d, after APPLY in IDLE %0d, after APPLY_NR in IDLE %0d; CPF_TRIM pin %0d; ERR 0x%02h; valid samples read %0d",
                 lvl0, lvl1, lvl2, CPF_TRIM, v, nvalid);
        $finish;
    end
endmodule
`default_nettype wire
