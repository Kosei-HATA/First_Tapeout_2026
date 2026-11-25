// round 44 check of auditor A's finding (rule (b) of requirements 5.4): the CRC-protected STATUS data byte, not the
// header, is what the host decides CMD_PENDING from. An illegal state value 9 is deposited into eeg_seq's state in
// the cycle of the tick that would take a pending FLUSH (IDLE); rule (b)'s three CRC STATUS reads (0x03) start 17
// frames after the command's CS_N rise. Counts, per read index, reads whose header / data byte has CMD_PENDING 1.
// +mhz1: 1 MHz SCLK; +fast: the fastest legal 2 MHz timing (spec 3.1: High 4 MCLK, t_css 5 MCLK, t_csh 3 MCLK,
// CS_N High 4 MCLK).
`timescale 1ns / 1ps
`default_nettype none
module tb_r44_pend_data;
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

    real    t_csr = 0.0, t_pend_fall = 0.0, t_ld = 0.0;
    integer errors = 0, n_inj = 0;
    logic   arm_inj = 1'b0;
    always @(posedge CS_N) t_csr = $realtime;
    always @(negedge dut.u_regs.pend) t_pend_fall = $realtime;
    always @(negedge MCLK)
        if (arm_inj && dut.u_clkgen.tick === 1'b1 && dut.u_regs.pend === 1'b1) begin
            dut.u_seq.state = 4'd9;
            arm_inj = 1'b0;
            n_inj = n_inj + 1;
        end

    integer hd [0:1][0:2];   // [inj][read] header CMD_PENDING 1
    integer dd [0:1][0:2];   // [inj][read] data byte CMD_PENDING 1
    real    worst [0:1];
    real    ld2_min = 1.0e9;  // earliest start of the second read's data byte, frames after the command's CS_N rise

    task automatic one(input integer offs, input integer inj);
        real t_cmd_csr, t17, t_rd;
        logic [7:0] v, err;
        integer e0;
        r14_write(7'h06, 8'hFF);
        @(posedge dut.u_clkgen.tick);
        repeat (offs) @(posedge MCLK);
        arm_inj = inj[0];
        r14_cmd(8'h55);
        t_cmd_csr = t_csr;
        t17 = t_cmd_csr + 17.0 * FRAME_NS;
        if ($realtime < t17) #(t17 - $realtime);
        for (int k = 0; k < 3; k++) begin
            t_rd = $realtime;
            e0 = spi_errors;
            r14_read(7'h03, v);
            if (spi_errors != e0) begin $display("ERROR: CRC/SPI error in read %0d", k); errors++; end
            if (spi_status[STATUS_CMD_PENDING_LSB] === 1'b1) hd[inj][k] = hd[inj][k] + 1;
            if (v[STATUS_CMD_PENDING_LSB] === 1'b1) dd[inj][k] = dd[inj][k] + 1;
            // the data byte is loaded at the synchronized SCLK fall after the header (spec 3.2): at the earliest
            // t_css + 7 periods + High after CS_N fall
            if (k == 1 && (t_rd + spi_tcss + 7.0 * (spi_high + spi_low) + spi_high - t_cmd_csr) / FRAME_NS < ld2_min)
                ld2_min = (t_rd + spi_tcss + 7.0 * (spi_high + spi_low) + spi_high - t_cmd_csr) / FRAME_NS;
        end
        wait (dut.u_regs.pend === 1'b0);
        arm_inj = 1'b0;
        if ((t_pend_fall - t_cmd_csr) / FRAME_NS > worst[inj]) worst[inj] = (t_pend_fall - t_cmd_csr) / FRAME_NS;
        r14_read(7'h06, err);
        if (inj == 0 && err !== 8'h00) begin $display("ERROR: ERR 0x%02h without injection", err); errors++; end
        if (inj == 1 && err !== 8'h40) begin $display("ERROR: ERR 0x%02h after injection", err); errors++; end
    endtask

    initial begin : main
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        if ($test$plusargs("mhz1")) begin spi_high = 500.0; spi_low = 500.0; end
        if ($test$plusargs("fast")) begin
            spi_high = 125.0; spi_low = 375.0; spi_tcss = 160.0; spi_tcsh = 100.0; spi_tidle = 130.0;
        end
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;          // CRC on (the procedure's mode after step 3)
        $display("SCLK high/low %0.0f/%0.0f ns, t_css %0.0f, t_csh %0.0f, CS_N high %0.0f ns, CRC on",
                 spi_high, spi_low, spi_tcss, spi_tcsh, spi_tidle);
        for (int rate = 0; rate < 2; rate++) begin
            r14_write(7'h26, rate ? 8'h01 : 8'h00);
            r14_cmd(8'h33);
            #(40000.0);
            if (dut.u_clkgen.fast !== rate[0]) begin $display("ERROR: rate not switched"); errors++; end
            for (int i = 0; i < 2; i++) begin
                worst[i] = 0.0;
                for (int k = 0; k < 3; k++) begin hd[i][k] = 0; dd[i][k] = 0; end
            end
            ld2_min = 1.0e9;
            for (int inj = 0; inj < 2; inj++)
                for (int offs = 0; offs < (rate ? 256 : 512); offs += 4) one(offs, inj);
            for (int inj = 0; inj < 2; inj++)
                $display("%0d kHz, %-13s: taken at most %0.2f frames after CS_N; of %0d phases, header CMD_PENDING 1 in reads 1/2/3: %0d/%0d/%0d, CRC data byte CMD_PENDING 1: %0d/%0d/%0d",
                         rate ? 128 : 64, inj ? "injection" : "no injection", worst[inj], (rate ? 256 : 512) / 4,
                         hd[inj][0], hd[inj][1], hd[inj][2], dd[inj][0], dd[inj][1], dd[inj][2]);
            $display("%0d kHz: the second read's data byte is loaded at the earliest %0.2f frames after the command's CS_N rise",
                     rate ? 128 : 64, ld2_min);
        end
        $display("tb_r44_pend_data done: %0d injections, errors %0d, SPI errors %0d", n_inj, errors, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
