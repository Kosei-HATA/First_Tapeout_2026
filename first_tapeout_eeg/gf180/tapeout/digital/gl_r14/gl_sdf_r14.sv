// gl_sdf_r14 - a representative SPI and sequencer test of the r14 macro at gate level (requirement VER-05; tracker C4),
// run with the SDF of the 3 corners and without delays, and the injection of illegal values into the netlist's
// sequencer and SPI state flip-flops (NFR-05).
//
// The RTL (dut, eeg_digital_top, the macro's parameters) runs in lockstep with the final netlist (gl_shadow_r14.sv,
// compiled as a second root with +define+TB=gl_sdf_r14): every one of the 50 outputs and the two state registers must
// be equal at every compare point, so every check below holds for the netlist as well. With the SDF, every
// asynchronous pin (RESET_N, SCLK, CS_N, MOSI) and CODE changes at an MCLK falling edge: TMCLK is 2 x 15.259 ns, the
// half period Icarus rounds #(T/2) to, and the SPI's times are whole periods (9 MCLK high and low, 1.82 MHz), so the
// netlist's synchronizers take each change at the same rising edge as the RTL's.
//
// Sequence (the checks count errors; the result line is printed at the end):
//   1  reset; ID 0xE6, VERSION 0x10, STATUS, ERR = RESET_FLAG and its W1C clear
//   2  SPI: register writes and reads (CRC off), a 4-byte burst read, CRC on (IF_CFG) with writes, reads and a sample
//      read of the empty FIFO, a wrong CRC (CRC_ERR, nothing written), a short write (FRAME_ERR), an undefined
//      address (ADDR_ERR), ERR read and cleared
//   3  sequencer: the timers at their minimum, offset range 1 / M 10, START: WARMUP, RECOVER, ALIGN, FILL, RUN (STATE
//      polled); samples read (VALID, CRC, SEQ consecutive); APPLY_NR M 11 (CHANGED on the next samples, OFM at the pins);
//      APPLY with CPF_TRIM 5 (AFE_RST pulse at the pin, PRE, PULSE ... RUN again, CPF_TRIM at the pins); FLUSH; STOP
//   4  illegal sequencer state values 9..15, forced into the RTL's state for one cycle (gl_shadow_r14 forces the same
//      value into the netlist's state flip-flops): IDLE and STATE_ERR at once, each from IDLE, and 13 from WARMUP
//   5  illegal SPI state values (the codes eeg_spi_slave does not use) inside a frame (CS_N low): FRAME_ERR and IDLE at
//      CS_N's rise, nothing written; and between frames: no flag, the next frame processed normally
//   6  SOFT_RESET: RESET_FLAG, the registers back to their reset values
`timescale 1ns / 1ps
`default_nettype none

module gl_sdf_r14;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 2.0 * 15.259;
    logic       MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    logic [4:0] CODE = 5'd16;
    wire        MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    wire        CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, CHOP1, OFS;
    wire [7:0]  TEST_CFG;
    wire [3:0]  CPF_TRIM, OFEN;
    wire [1:0]  AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0]  OFM;

    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    // CODE: once per frame, at the falling edge after frame cycle 2 (eeg_adc_dig changes it at e2)
    always @(negedge MCLK) if (dut.cycle == 5'd2) CODE <= 5'(8 + $urandom_range(0, 16));

    `include "spi_bfm_r14.svh"

    integer errors = 0;
    task automatic fail(input string msg);
        errors = errors + 1;
        if (errors <= 40) $display("ERROR @%0t: %s", $time, msg);
    endtask
    // every SPI frame starts at a falling edge (the BFM's times are whole MCLK periods)
    task automatic wr(input logic [6:0] a, input logic [7:0] v);
        @(negedge MCLK); r14_write(a, v);
    endtask
    task automatic rd(input logic [6:0] a, output logic [7:0] v);
        @(negedge MCLK); r14_read(a, v);
    endtask
    task automatic rd_expect(input logic [6:0] a, input logic [7:0] e, input string what);
        logic [7:0] v;
        rd(a, v);
        if (v !== e) fail($sformatf("%s: read 0x%02h = 0x%02h, expected 0x%02h", what, a, v, e));
    endtask
    task automatic cmd(input logic [7:0] c);
        wr(A_COMMAND, c);
    endtask
    task automatic wait_state(input logic [3:0] s, input real tmax_us, input string what);
        logic [7:0] v;
        realtime t0;
        t0 = $realtime;
        forever begin
            rd(A_STATE, v);
            if (v[3:0] == s) break;
            if ($realtime - t0 > tmax_us * 1000.0) begin
                fail($sformatf("%s: STATE %0d, not %0d after %0.0f us", what, v[3:0], s, tmax_us));
                break;
            end
            repeat (512) @(negedge MCLK);
        end
    endtask
    integer n_samples = 0, n_changed = 0;
    logic [15:0] last_seq;
    bit have_seq = 0;
    task automatic sample(input string what, output logic [7:0] st);
        logic [15:0] sq; logic [23:0] d; bit ok;
        while (DRDY_N !== 1'b0) @(negedge MCLK);
        @(negedge MCLK);
        r14_sample(st, sq, d, ok);
        n_samples = n_samples + 1;
        if (!st[SMP_VALID_LSB]) fail($sformatf("%s: sample not VALID (status 0x%02h)", what, st));
        if (!ok) fail($sformatf("%s: sample CRC wrong", what));
        if (have_seq && sq !== 16'(last_seq + 16'd1) && !st[SMP_CHANGED_LSB])
            ;                                                   // SEQ gaps are legal across an APPLY (not stored)
        last_seq = sq; have_seq = 1;
        if (st[SMP_CHANGED_LSB]) n_changed = n_changed + 1;
    endtask
    // the illegal SPI state values: the codes eeg_spi_slave does not use, read from the compiled RTL
    logic [15:0] spi_defd;
    task automatic force_spi_st(input integer v);
        case (v)
            0: force dut.u_spi.st = 4'd0;    1: force dut.u_spi.st = 4'd1;    2: force dut.u_spi.st = 4'd2;
            3: force dut.u_spi.st = 4'd3;    4: force dut.u_spi.st = 4'd4;    5: force dut.u_spi.st = 4'd5;
            6: force dut.u_spi.st = 4'd6;    7: force dut.u_spi.st = 4'd7;    8: force dut.u_spi.st = 4'd8;
            9: force dut.u_spi.st = 4'd9;    10: force dut.u_spi.st = 4'd10;  11: force dut.u_spi.st = 4'd11;
            12: force dut.u_spi.st = 4'd12;  13: force dut.u_spi.st = 4'd13;  14: force dut.u_spi.st = 4'd14;
            default: force dut.u_spi.st = 4'd15;
        endcase
    endtask
    task automatic force_seq(input integer v);
        case (v)
            9: force dut.u_seq.state = 4'd9;    10: force dut.u_seq.state = 4'd10;  11: force dut.u_seq.state = 4'd11;
            12: force dut.u_seq.state = 4'd12;  13: force dut.u_seq.state = 4'd13;  14: force dut.u_seq.state = 4'd14;
            default: force dut.u_seq.state = 4'd15;
        endcase
    endtask
    // The forced value appears INJ after a rising edge, about when a flip-flop's Q changes in the netlist: after the clock
    // tree (the flip-flops' clock 2-4 ns after the pin at ss) and the clock-to-output delay. Forced 1 ps after the edge,
    // with the SDF the flip-flops would still take that edge, with a D computed from the forced value (11/24: AFE_RST took
    // a 0 there in all three corners, 4 of the 8 injections). Without delays any time in the cycle is the same.
    localparam real INJ = 5.0;
    // one cycle: forced INJ after a rising edge, released at the next one (the RTL takes its next state there)
    task automatic inject_seq(input integer v);
        @(posedge MCLK); #(INJ);
        force_seq(v);
        @(posedge MCLK);
        release dut.u_seq.state;
    endtask

    integer n_inj_seq = 0, n_inj_spi_in = 0, n_inj_spi_out = 0;
    logic [7:0] v, st;
    realtime t_rst_rise, t_rst_fall, pulse_w;
    integer pulses = 0;
    always @(posedge AFE_RST) t_rst_rise = $realtime;
    always @(negedge AFE_RST) begin t_rst_fall = $realtime; pulses = pulses + 1; end

    initial begin
        spi_high = 9.0 * TMCLK;  spi_low = 9.0 * TMCLK;  spi_tcss = 10.0 * TMCLK;
        spi_tcsh = 7.0 * TMCLK;  spi_tidle = 20.0 * TMCLK;
        repeat (10) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        // ---------------- 1: identity and the reset flag
        rd_expect(A_ID, 8'hE6, "1 ID");
        rd_expect(A_VERSION, 8'h10, "1 VERSION");
        rd_expect(A_ERR, 8'h01, "1 ERR after reset (RESET_FLAG)");
        wr(A_ERR, 8'h01);
        rd_expect(A_ERR, 8'h00, "1 ERR after its W1C");
        rd_expect(A_STATE, {4'h0, ST_IDLE}, "1 STATE");
        $display("1  identity, RESET_FLAG (errors %0d)", errors);
`ifndef GL_DBG_SKIP23                                       // a debugging run straight to 4 (not in the record)
        // ---------------- 2: SPI
        wr(A_CPF_TRIM, 8'h0E);
        rd_expect(A_CPF_TRIM, 8'h0E, "2 CPF_TRIM written");
        wr(A_ALERT_MASK, 8'h5A);
        rd_expect(A_ALERT_MASK, 8'h5A, "2 ALERT_MASK written");
        // a burst read from ID: ID, VERSION, CAPS, STATUS (CRC off: the address increments)
        @(negedge MCLK);
        spi_tx[0] = {1'b1, A_ID}; for (int i = 1; i < 6; i++) spi_tx[i] = 8'h00;
        spi_xfer(5, 0);
        if (spi_rx[1] !== 8'hE6 || spi_rx[2] !== 8'h10) fail($sformatf("2 burst: 0x%02h 0x%02h", spi_rx[1], spi_rx[2]));
        rd_expect(A_ERR, 8'h00, "2 ERR after the burst");
        // CRC on
        wr(A_IF_CFG, 8'h01);
        bfm_crc_en = 1'b1;
        wr(A_CPF_TRIM, 8'h07);
        rd_expect(A_CPF_TRIM, 8'h07, "2 CPF_TRIM written with CRC");
        rd_expect(A_ERR, 8'h00, "2 ERR with CRC on");
        begin   // a sample read of the empty FIFO: VALID 0, the frame's CRC right
            logic [15:0] sq; logic [23:0] d; bit ok;
            @(negedge MCLK); r14_sample(st, sq, d, ok);
            if (st[SMP_VALID_LSB] !== 1'b0 || !ok) fail($sformatf("2 empty sample: status 0x%02h crc %0d", st, ok));
        end
        // a wrong CRC: CRC_ERR, nothing written
        @(negedge MCLK);
        spi_tx[0] = {1'b0, A_CPF_TRIM}; spi_tx[1] = 8'h03; spi_tx[2] = 8'hFF ^ tb_crc8_update(tb_crc8_update(8'h00, spi_tx[0]), 8'h03);
        spi_xfer(3, 0);
        rd_expect(A_ERR, 8'h04, "2 ERR after a wrong CRC (CRC_ERR)");
        rd_expect(A_CPF_TRIM, 8'h07, "2 CPF_TRIM kept after a wrong CRC");
        wr(A_ERR, 8'hFF);
        // a short write (header and data, no CRC byte, CRC on): FRAME_ERR
        @(negedge MCLK);
        spi_tx[0] = {1'b0, A_CPF_TRIM}; spi_tx[1] = 8'h03;
        spi_xfer(2, 0);
        rd_expect(A_ERR, 8'h02, "2 ERR after a short write (FRAME_ERR)");
        wr(A_ERR, 8'hFF);
        // an undefined address
        rd(7'h7F, v);
        rd_expect(A_ERR, 8'h08, "2 ERR after a read of 0x7F (ADDR_ERR)");
        wr(A_ERR, 8'hFF);
        rd_expect(A_ERR, 8'h00, "2 ERR cleared");
        $display("2  SPI: writes, reads, burst, CRC, empty sample, CRC_ERR, FRAME_ERR, ADDR_ERR (errors %0d)", errors);
        // ---------------- 3: sequencer
        wr(A_T_WARM, T_WARM_T_WARM_MIN);  wr(A_T_REC, T_REC_T_REC_MIN);
        wr(A_T_PRE, T_PRE_T_PRE_MIN);     wr(A_T_RST, T_RST_T_RST_MIN);
        wr(A_OFF_CTRL, 8'h01);            wr(A_OFF_M_H, 8'h00);   wr(A_OFF_M_L, 8'd10);
        cmd(CMD_START);
        wait_state(ST_RUN, 12000.0, "3 START");
        if (OFM !== 10'd10 || OFEN !== ofen_of_range(3'd1)) fail($sformatf("3 OFM %0d OFEN %b after START", OFM, OFEN));
        for (int i = 0; i < 2; i++) sample("3 RUN", st);
        // APPLY_NR: one step
        wr(A_OFF_M_L, 8'd11);
        cmd(CMD_APPLY_NR);
        repeat (600) @(negedge MCLK);
        if (OFM !== 10'd11) fail($sformatf("3 OFM %0d after APPLY_NR", OFM));
        for (int i = 0; i < 4; i++) sample("3 after APPLY_NR", st);
        if (n_changed == 0) fail("3 no sample with CHANGED after APPLY_NR");
        rd_expect(A_ERR, 8'h00, "3 ERR after APPLY_NR");
        // APPLY: a new CPF_TRIM with the AFE_RST pulse and the re-settling
        pulses = 0;
        wr(A_CPF_TRIM, 8'h05);
        cmd(CMD_APPLY);
        wait_state(ST_RUN, 6000.0, "3 APPLY");
        pulse_w = t_rst_fall - t_rst_rise;
        if (pulses != 1) fail($sformatf("3 APPLY: %0d AFE_RST pulses", pulses));
        else if (pulse_w < 95000.0) fail($sformatf("3 APPLY: AFE_RST pulse %0.1f us", pulse_w / 1000.0));
        if (CPF_TRIM !== 4'd5) fail($sformatf("3 CPF_TRIM %0d after APPLY", CPF_TRIM));
        sample("3 after APPLY", st);
        cmd(CMD_FLUSH);
        repeat (600) @(negedge MCLK);
        rd_expect(A_FIFO_LEVEL, 8'h00, "3 FIFO_LEVEL after FLUSH");
        cmd(CMD_STOP);
        wait_state(ST_IDLE, 100.0, "3 STOP");
        rd_expect(A_ERR, 8'h00, "3 ERR at the end");
        $display("3  START to RUN, %0d samples, APPLY_NR (%0d CHANGED), APPLY (AFE_RST %0.1f us), FLUSH, STOP (errors %0d)",
                 n_samples, n_changed, pulse_w / 1000.0, errors);
`else
        wr(A_IF_CFG, 8'h01);
        bfm_crc_en = 1'b1;
        wr(A_T_WARM, T_WARM_T_WARM_MIN);  wr(A_T_REC, T_REC_T_REC_MIN);
        wr(A_OFF_CTRL, 8'h01);            wr(A_OFF_M_H, 8'h00);   wr(A_OFF_M_L, 8'd11);
        wr(A_CPF_TRIM, 8'h05);
`endif
`ifdef GL_DBG_VCD
        $dumpfile(`GL_DBG_VCD);
        $dumpvars(0, gl_sdf_r14.dut.u_seq, gl_sdf_r14.AFE_RST, gl_sdf_r14.MCLK, gl_shadow_r14.afe_rst, gl_shadow_r14.seq_gl,
                  gl_shadow_r14.seq_rtl, gl_shadow_r14.t_pos, gl_shadow_r14.seq_hold);
`endif
        // ---------------- 4: illegal sequencer states
        for (int bad = 9; bad <= 15; bad++) begin
            inject_seq(bad);
            n_inj_seq = n_inj_seq + 1;
            @(negedge MCLK);
            if (dut.seq_state !== ST_IDLE) fail($sformatf("4 state %0d after the illegal %0d", dut.seq_state, bad));
            if (AFE_RST !== 1'b1) fail($sformatf("4 AFE_RST %b after the illegal %0d", AFE_RST, bad));
            rd_expect(A_ERR, 8'h40, $sformatf("4 ERR after the illegal sequencer state %0d (STATE_ERR)", bad));
            wr(A_ERR, 8'hFF);
            rd_expect(A_STATE, {4'h0, ST_IDLE}, $sformatf("4 STATE after the illegal %0d", bad));
        end
        cmd(CMD_START);                                         // and once from WARMUP (the AFE starting)
        wait_state(ST_WARMUP, 200.0, "4 START");
        inject_seq(13);
        n_inj_seq = n_inj_seq + 1;
        @(negedge MCLK);
        if (dut.seq_state !== ST_IDLE || AFE_RST !== 1'b1) fail("4 not IDLE with AFE_RST after the illegal 13 in WARMUP");
        rd_expect(A_ERR, 8'h40, "4 ERR after the illegal 13 in WARMUP");
        wr(A_ERR, 8'hFF);
        repeat (2000) @(negedge MCLK);
        rd_expect(A_STATE, {4'h0, ST_IDLE}, "4 STATE stays IDLE after the illegal 13 in WARMUP");
        $display("4  illegal sequencer states 9..15 from IDLE and 13 from WARMUP: IDLE, AFE_RST, STATE_ERR (%0d, errors %0d)", n_inj_seq, errors);
        // ---------------- 5: illegal SPI states
        spi_defd = 16'h0;
        spi_defd[dut.u_spi.S_IDLE] = 1'b1;  spi_defd[dut.u_spi.S_HDR] = 1'b1;   spi_defd[dut.u_spi.S_RREG] = 1'b1;
        spi_defd[dut.u_spi.S_RCRC] = 1'b1;  spi_defd[dut.u_spi.S_RDONE] = 1'b1; spi_defd[dut.u_spi.S_RSMP] = 1'b1;
        spi_defd[dut.u_spi.S_SDONE] = 1'b1; spi_defd[dut.u_spi.S_WDAT] = 1'b1;  spi_defd[dut.u_spi.S_WCRC] = 1'b1;
        spi_defd[dut.u_spi.S_WDONE] = 1'b1; spi_defd[dut.u_spi.S_OVF] = 1'b1;
        for (int bad = 0; bad < 16; bad++) if (!spi_defd[bad]) begin
            @(negedge MCLK);
            fork
                begin
                    spi_tx[0] = {1'b0, A_CPF_TRIM}; spi_tx[1] = 8'h0E;
                    spi_tx[2] = tb_crc8_update(tb_crc8_update(8'h00, spi_tx[0]), 8'h0E);
                    spi_xfer(3, 0);
                end
                begin
                    repeat (200) @(posedge MCLK);               // inside the data byte
                    #(INJ); force_spi_st(bad);
                    @(posedge MCLK);
                    release dut.u_spi.st;
                end
            join
            if (dut.u_spi.st !== dut.u_spi.S_IDLE)
                fail($sformatf("5 SPI state %0d after the CS_N rise of the frame with the illegal %0d", dut.u_spi.st, bad));
            n_inj_spi_in = n_inj_spi_in + 1;
            rd_expect(A_ERR, 8'h02, $sformatf("5 FRAME_ERR for the illegal SPI state %0d in a frame", bad));
            wr(A_ERR, 8'hFF);
            rd_expect(A_CPF_TRIM, 8'h05, $sformatf("5 CPF_TRIM not written with the illegal SPI state %0d", bad));
        end
        for (int bad = 0; bad < 16; bad++) if (!spi_defd[bad]) begin
            @(posedge MCLK); #(INJ);
            force_spi_st(bad);
            @(posedge MCLK);
            release dut.u_spi.st;
            repeat (4) @(negedge MCLK);
            if (dut.u_spi.st !== bad[3:0]) fail($sformatf("5 SPI state %0d forced between frames was %0d", bad, dut.u_spi.st));
            n_inj_spi_out = n_inj_spi_out + 1;
            wr(A_CPF_TRIM, 8'h0E);
            rd_expect(A_ERR, 8'h00, $sformatf("5 no flag after the illegal SPI state %0d between frames", bad));
            rd_expect(A_CPF_TRIM, 8'h0E, $sformatf("5 the frame after the illegal SPI state %0d", bad));
            wr(A_CPF_TRIM, 8'h05);
        end
        $display("5  illegal SPI states: %0d inside frames (FRAME_ERR, IDLE), %0d between frames (no flag) (errors %0d)",
                 n_inj_spi_in, n_inj_spi_out, errors);
        // ---------------- 6: SOFT_RESET
        cmd(CMD_SOFT_RESET);
        bfm_crc_en = 1'b0;                                      // IF_CFG back to its reset value
        repeat (20) @(negedge MCLK);
        rd_expect(A_ERR, 8'h01, "6 ERR after SOFT_RESET (RESET_FLAG)");
        rd_expect(A_CPF_TRIM, 8'h08, "6 CPF_TRIM after SOFT_RESET");
        rd_expect(A_IF_CFG, 8'h00, "6 IF_CFG after SOFT_RESET");
        $display("6  SOFT_RESET (errors %0d)", errors);
        repeat (100) @(negedge MCLK);
        if (spi_errors != 0) fail($sformatf("%0d SPI errors", spi_errors));
        if (errors == 0) $display("PASS: gl_sdf_r14 (%0d SPI frames)", spi_xfers);
        else             $display("FAIL: gl_sdf_r14, %0d errors", errors);
        $finish;
    end
endmodule
`default_nettype wire
