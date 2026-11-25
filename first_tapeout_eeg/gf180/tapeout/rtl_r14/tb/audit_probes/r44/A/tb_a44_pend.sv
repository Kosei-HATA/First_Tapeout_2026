// audit 44 A probe: rule (b) of requirements 5.4 says that 17 frames after a command's CS_N rise the command "is
// always taken at a tick, so the true CMD_PENDING is 0". NFR-05 (eeg_seq.sv 95-97) handles an illegal state value
// before the tick and keeps the pending command (no cmd_ack) for the next tick. This bench deposits the illegal value 9
// into eeg_seq's state register during the tick cycle that would take a pending FLUSH (IDLE, 64 kHz and 128 kHz) and
// measures when CMD_PENDING falls relative to the command's CS_N rise, with rule (b)'s STATUS reads started 17 frames
// after it (2 MHz, the BFM's default gaps), until one returns CMD_PENDING 0.
`timescale 1ns / 1ps
`default_nettype none
module tb_a44_pend;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    localparam real FRAME_NS = 32.0 * 1000.0 / 32.768;
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

    real    t_csr = 0.0, t_pend_fall = 0.0;
    integer errors = 0, n_inj = 0;
    logic   arm_inj = 1'b0;
    always @(posedge CS_N) t_csr = $realtime;
    always @(negedge dut.u_regs.pend) t_pend_fall = $realtime;
    // the injection: in the cycle of the tick that would take the pending command, the state register holds 9
    always @(negedge MCLK)
        if (arm_inj && dut.u_clkgen.tick === 1'b1 && dut.u_regs.pend === 1'b1) begin
            dut.u_seq.state = 4'd9;
            arm_inj = 1'b0;
            n_inj = n_inj + 1;
        end

    task automatic one(input integer offs, input bit inject, output real d_frames, output integer nread1,
                       output logic [7:0] err);
        real t_cmd_csr, t17;
        logic [7:0] v;
        r14_write(7'h06, 8'hFF);                         // ERR cleared
        @(posedge dut.u_clkgen.tick);
        repeat (offs) @(posedge MCLK);
        arm_inj = inject;
        r14_cmd(8'h55);                                  // FLUSH in IDLE (pending until a tick)
        t_cmd_csr = t_csr;
        t17 = t_cmd_csr + 17.0 * FRAME_NS;
        if ($realtime < t17) #(t17 - $realtime);
        nread1 = 0;                                      // rule (b): CRC-off here; the STATUS byte of each read
        for (int k = 0; k < 4; k++) begin
            r14_read(7'h03, v);
            if (spi_status[STATUS_CMD_PENDING_LSB] === 1'b1) nread1 = nread1 + 1;
            else break;
        end
        wait (dut.u_regs.pend === 1'b0);
        arm_inj = 1'b0;
        d_frames = (t_pend_fall - t_cmd_csr) / FRAME_NS;
        r14_read(7'h06, err);
    endtask

    initial begin : main
        real d, worst;
        integer n1, worst_offs, n_ones, n_two;
        logic [7:0] e;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        if ($test$plusargs("mhz1")) begin spi_high = 500.0; spi_low = 500.0; end     // 1 MHz SCLK
        if ($test$plusargs("crc")) begin r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1; end   // CRC on (IF_CFG)
        $display("SCLK high/low %0.0f/%0.0f ns, CRC %0d", spi_high, spi_low, bfm_crc_en);
        for (int rate = 0; rate < 2; rate++) begin
            // rate 0: 64 kHz (CHOP_FAST 0 applied in IDLE), rate 1: 128 kHz (the reset value)
            r14_write(7'h26, rate ? 8'h01 : 8'h00);
            r14_cmd(8'h33);                                // APPLY in IDLE: no pulse, applied at the tick
            #(40000.0);
            if (dut.u_clkgen.fast !== rate[0]) begin $display("ERROR: rate not switched"); errors++; end
            for (int inj = 0; inj < 2; inj++) begin
                worst = 0.0; worst_offs = -1; n_ones = 0; n_two = 0;
                for (int offs = 0; offs < (rate ? 256 : 512); offs += 4) begin
                    one(offs, inj[0], d, n1, e);
                    if (d > worst) begin worst = d; worst_offs = offs; end
                    if (n1 > 0) n_ones = n_ones + 1;
                    if (n1 > 1) n_two = n_two + 1;
                    if (inj == 0 && (n1 != 0 || e !== 8'h00)) begin
                        $display("ERROR: no injection, %0d kHz, offset %0d: %0d reads with CMD_PENDING 1, ERR 0x%02h", rate ? 128 : 64, offs, n1, e);
                        errors++;
                    end
                    if (inj == 1 && e !== 8'h40) begin
                        $display("ERROR: injection, %0d kHz, offset %0d: ERR 0x%02h, expected STATE_ERR 0x40", rate ? 128 : 64, offs, e);
                        errors++;
                    end
                end
                $display("%0d kHz, %-58s: taken at most %0.2f frames after CS_N (offset %0d MCLK after a tick); %0d of %0d phases had rule (b)'s first read (17 frames) return CMD_PENDING 1, %0d of them two reads",
                         rate ? 128 : 64, inj ? "illegal state value 9 in the cycle of the taking tick" : "no injection",
                         worst, worst_offs, n_ones, (rate ? 256 : 512) / 4, n_two);
            end
        end
        $display("tb_a44_pend done: %0d injections, errors %0d, SPI errors %0d", n_inj, errors, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
