// tb_host_r15 - VER-06 (11/28): the board for the Python host model (tb/host_r15.py). Two r15 chips (dut0, dut1) share
// MCLK, RESET_N, SCLK and MOSI; each has its own CS_N and DRDY_N; MISO is one line driven through MISO_OE (pad delay
// 15 ns) with a pull-up, as requirement 5.4 rule (a) assumes. Each chip has a model of its analog front end and ADC:
//   electrode offset v_off + a common sine (+ noise), minus the offset DAC from the pins (OFM, OFS, OFEN: (1 - 2 OFS)
//   x the M bits of the enabled groups x 301 uV, the measured step at the amplifier input), times the AFE gain 287.02,
//   0 while AFE_RST is high; a first-order sigma-delta with the 31 odd levels of the CIC input (x = 31 v / 0.5 V, the
//   error held to +-40: a large input sticks at the codes 0 / 31, which the overload detector flags). CODE changes at
//   frame cycle 1 (e2), as eeg_adc_dig's.
// The host model drives the board through two named pipes (+pin=<fifo> commands, +pout=<fifo> answers), one line each:
// 20 integers per command, op first:
//   1 X chip nbits nbytes b0..b15  SPI frame on that CS_N (nbits SCLK pulses, MOSI from the bytes, then 0): answer
//                                 "1 t_ns m0..m15" with MISO as sampled at each SCLK rise (bits past nbits 0);
//                                 chip + 4: keep CS_N low at the end; chip + 8: go on with the frame left open
//   2 W ns                         wait
//   3 D chip mode timeout_ns       wait for DRDY_N: mode 0 its level Low, 1 a falling edge; chip 2 = a falling edge of
//                                 each chip (answer the two times in ps, -1 for none); chip 3 = either DRDY_N Low
//   4 G                            DRDY_N of both chips now
//   5 R v                          RESET_N <= v (at an MCLK falling edge)
//   6 V chip off_uV sine_uV sine_mHz noise_uV   the analog model's input
//   7 O chip                       the oracle (for the host model's checks, never its decisions): state, SEQ, FIFO
//                                 level, ERR, DFLAG, CRC_EN, applies, the active M, SIGN, RANGE, the residual in uV
//   8 K high low tcss tcsh tidle   SCLK timing in ns (default 250 250 300 200 600: 2 MHz)
//   9 Q                            finish
// Every frame and RESET_N change starts 1 ns after an MCLK falling edge, never at a rising edge. Answers start with the
// op and the time in ns. The board checks the MISO line for contention (both MISO_OE high).
`timescale 1ns / 1ps
`default_nettype none

module tb_host_r15;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    localparam real GAIN = 287.02;
    localparam real STEP_UV = 301.0;
    localparam real VREF = 0.5;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, MOSI = 1'b0;
    logic [1:0] CS_N = 2'b11;
    always #(TMCLK / 2.0) MCLK = ~MCLK;

    // ---------------- the two chips
    wire        MISO0, MISO_OE0, DRDY_N0, RAW_DATA0, RAW_CLK0, ADC_RST_N0, TH_CAPTURE0, DAC_LOAD0, DWA_EN0;
    wire        CMP_STROBE0, DAC_CLK0, CHOP0, CHOP_OUT0, CHOP_BLANK0, AFE_RST0, CHOP_EN0, OFS0, CHOP10;
    wire [7:0]  TEST_CFG0;
    wire [3:0]  CPF_TRIM0, OFEN0;
    wire [1:0]  AFE_IBIAS0, BTRIM_P0, BTRIM_N0;
    wire [9:0]  OFM0;
    logic [4:0] CODE0 = 5'd16;
    wire        MISO1, MISO_OE1, DRDY_N1, RAW_DATA1, RAW_CLK1, ADC_RST_N1, TH_CAPTURE1, DAC_LOAD1, DWA_EN1;
    wire        CMP_STROBE1, DAC_CLK1, CHOP1_, CHOP_OUT1, CHOP_BLANK1, AFE_RST1, CHOP_EN1, OFS1, CHOP11;
    wire [7:0]  TEST_CFG1;
    wire [3:0]  CPF_TRIM1, OFEN1;
    wire [1:0]  AFE_IBIAS1, BTRIM_P1, BTRIM_N1;
    wire [9:0]  OFM1;
    logic [4:0] CODE1 = 5'd16;

    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut0 (
        .MCLK(MCLK), .RESET_N(RESET_N), .SCLK(SCLK), .CS_N(CS_N[0]), .MOSI(MOSI), .MISO(MISO0), .MISO_OE(MISO_OE0),
        .DRDY_N(DRDY_N0), .RAW_DATA(RAW_DATA0), .RAW_CLK(RAW_CLK0), .ADC_RST_N(ADC_RST_N0), .TH_CAPTURE(TH_CAPTURE0),
        .DAC_LOAD(DAC_LOAD0), .DWA_EN(DWA_EN0), .CODE(CODE0), .CMP_STROBE(CMP_STROBE0), .DAC_CLK(DAC_CLK0),
        .CHOP(CHOP0), .CHOP_OUT(CHOP_OUT0), .CHOP_BLANK(CHOP_BLANK0), .AFE_RST(AFE_RST0), .CHOP_EN(CHOP_EN0),
        .TEST_CFG(TEST_CFG0), .CPF_TRIM(CPF_TRIM0), .AFE_IBIAS(AFE_IBIAS0), .BTRIM_P(BTRIM_P0), .BTRIM_N(BTRIM_N0),
        .OFM(OFM0), .OFS(OFS0), .OFEN(OFEN0), .CHOP1(CHOP10));
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut1 (
        .MCLK(MCLK), .RESET_N(RESET_N), .SCLK(SCLK), .CS_N(CS_N[1]), .MOSI(MOSI), .MISO(MISO1), .MISO_OE(MISO_OE1),
        .DRDY_N(DRDY_N1), .RAW_DATA(RAW_DATA1), .RAW_CLK(RAW_CLK1), .ADC_RST_N(ADC_RST_N1), .TH_CAPTURE(TH_CAPTURE1),
        .DAC_LOAD(DAC_LOAD1), .DWA_EN(DWA_EN1), .CODE(CODE1), .CMP_STROBE(CMP_STROBE1), .DAC_CLK(DAC_CLK1),
        .CHOP(CHOP1_), .CHOP_OUT(CHOP_OUT1), .CHOP_BLANK(CHOP_BLANK1), .AFE_RST(AFE_RST1), .CHOP_EN(CHOP_EN1),
        .TEST_CFG(TEST_CFG1), .CPF_TRIM(CPF_TRIM1), .AFE_IBIAS(AFE_IBIAS1), .BTRIM_P(BTRIM_P1), .BTRIM_N(BTRIM_N1),
        .OFM(OFM1), .OFS(OFS1), .OFEN(OFEN1), .CHOP1(CHOP11));

    // ---------------- the MISO line: pad delay, MISO_OE, pull-up; contention
    localparam real TPAD = 15.0;
    wire #(TPAD) m0_pin = MISO0;
    wire #(TPAD) o0_pin = MISO_OE0;
    wire #(TPAD) m1_pin = MISO1;
    wire #(TPAD) o1_pin = MISO_OE1;
    wire miso_line = o0_pin === 1'b1 ? m0_pin : (o1_pin === 1'b1 ? m1_pin : 1'b1);
    integer n_contention = 0;
    always @(MISO_OE0 or MISO_OE1)
        if (MISO_OE0 === 1'b1 && MISO_OE1 === 1'b1) begin
            n_contention = n_contention + 1;
            if (n_contention <= 5) $display("BOARD ERROR @%0t: both chips drive MISO", $time);
        end

    // ---------------- the analog model
    real v_off_uv [0:1];
    real noise_uv [0:1];
    real sine_uv = 0.0, sine_hz = 0.0;
    real sd_err [0:1];
    real resid_uv [0:1];
    integer seed0 = 11, seed1 = 23;
    initial begin
        v_off_uv[0] = 0.0; v_off_uv[1] = 0.0; noise_uv[0] = 0.0; noise_uv[1] = 0.0;
        sd_err[0] = 0.0; sd_err[1] = 0.0; resid_uv[0] = 0.0; resid_uv[1] = 0.0;
    end
    function automatic integer dac_steps(input logic [9:0] ofm, input logic ofs, input logic [3:0] ofen);
        integer m;
        m = (ofen[0] ? ofm[6:0] : 0) + (ofen[1] ? {ofm[7], 7'd0} : 0) + (ofen[2] ? {ofm[8], 8'd0} : 0)
          + (ofen[3] ? {ofm[9], 9'd0} : 0);
        return ofs ? -m : m;
    endfunction
    function automatic logic [4:0] sd_code(input integer k, input real x);
        real v, lv;
        integer lvl;
        v = x + sd_err[k];
        lvl = 2 * $rtoi($floor((v + 31.0) / 2.0 + 0.5)) - 31;
        if (lvl > 31) lvl = 31;
        if (lvl < -31) lvl = -31;
        lv = lvl;
        sd_err[k] = v - lv;
        if (sd_err[k] > 40.0) sd_err[k] = 40.0;
        if (sd_err[k] < -40.0) sd_err[k] = -40.0;
        return 5'((lvl + 31) / 2);
    endfunction
    function automatic real adc_x(input integer k, input logic afe_rst, input logic [9:0] ofm, input logic ofs,
                                  input logic [3:0] ofen);
        real r, n;
        integer s;
        r = v_off_uv[k] + sine_uv * $sin(2.0 * 3.141592653589793 * sine_hz * $realtime * 1.0e-9)
            - STEP_UV * dac_steps(ofm, ofs, ofen);
        if (noise_uv[k] > 0.0) begin
            if (k == 0) s = $dist_normal(seed0, 0, 1000000); else s = $dist_normal(seed1, 0, 1000000);
            n = noise_uv[k] * s / 1.0e6;
            r = r + n;
        end
        resid_uv[k] = r;
        if (afe_rst) return 0.0;
        return 31.0 * (GAIN * r * 1.0e-6) / VREF;
    endfunction
    always @(posedge MCLK) begin
        if (RESET_N && dut0.cycle == 5'd1) CODE0 <= sd_code(0, adc_x(0, AFE_RST0, OFM0, OFS0, OFEN0));
        if (RESET_N && dut1.cycle == 5'd1) CODE1 <= sd_code(1, adc_x(1, AFE_RST1, OFM1, OFS1, OFEN1));
    end

    // ---------------- DRDY_N falling edges (time stamps)
    real t_fall [0:1];
    integer n_fall [0:1];
    initial begin t_fall[0] = -1.0; t_fall[1] = -1.0; n_fall[0] = 0; n_fall[1] = 0; end
    always @(negedge DRDY_N0) begin t_fall[0] = $realtime; n_fall[0] = n_fall[0] + 1; end
    always @(negedge DRDY_N1) begin t_fall[1] = $realtime; n_fall[1] = n_fall[1] + 1; end

    // ---------------- SPI frames
    real t_high = 250.0, t_low = 250.0, t_css = 300.0, t_csh = 200.0, t_idle = 600.0;
    logic [7:0] txb [0:15];
    logic [7:0] rxb [0:15];
    integer n_frames = 0;
    // keep: leave CS_N low after the last SCLK fall (the host decides on the rest of the frame); cont: go on with a
    // frame left open by keep (no CS_N fall, the SCLK low time first)
    task automatic xfer(input integer chip, input integer nbits, input bit keep, input bit cont);
        for (int i = 0; i < 16; i++) rxb[i] = 8'h00;
        if (!cont) begin
            @(negedge MCLK);
            #1;
            CS_N[chip] = 1'b0;
            MOSI = (nbits > 0) ? txb[0][7] : 1'b0;
            #(t_css);
        end else begin
            MOSI = (nbits > 0) ? txb[0][7] : 1'b0;
            if (nbits > 0) #(t_low);
        end
        for (int n = 0; n < nbits; n++) begin
            SCLK = 1'b1;
            if (n < 128) rxb[n / 8][7 - (n % 8)] = (miso_line === 1'b1);
            #(t_high);
            SCLK = 1'b0;
            MOSI = (n + 1 < nbits && n + 1 < 128) ? txb[(n + 1) / 8][7 - ((n + 1) % 8)] : 1'b0;
            if (n + 1 < nbits) #(t_low);
        end
        if (!keep) begin
            #(t_csh);
            CS_N[chip] = 1'b1;
            #(t_idle);
            n_frames = n_frames + 1;
        end
    endtask

    // ---------------- the command loop
    string pin_name, pout_name;
    integer fin, fout, rc, nf;
    reg [8*400-1:0] line;
    longint f [0:19];
    real t0;
    integer found0, found1;
    longint ta, tb;
    initial begin
        if (!$value$plusargs("pin=%s", pin_name) || !$value$plusargs("pout=%s", pout_name)) begin
            $display("FAIL: tb_host_r15 needs +pin=<fifo> +pout=<fifo>");
            $finish;
        end
        fin = $fopen(pin_name, "r");
        fout = $fopen(pout_name, "w");
        forever begin
            line = '0;
            rc = $fgets(line, fin);
            if (rc == 0) begin $display("tb_host_r15: the host closed the pipe"); $finish; end
            for (int i = 0; i < 20; i++) f[i] = 0;
            nf = $sscanf(line, "%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d", f[0], f[1], f[2], f[3],
                         f[4], f[5], f[6], f[7], f[8], f[9], f[10], f[11], f[12], f[13], f[14], f[15], f[16], f[17],
                         f[18], f[19]);
            case (f[0])
                1: begin
                    for (int i = 0; i < 16; i++) txb[i] = (i < f[3]) ? f[4 + i][7:0] : 8'h00;
                    xfer(f[1] % 4, f[2], f[1][2], f[1][3]);
                    $fdisplay(fout, "1 %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                              longint'($realtime), rxb[0], rxb[1], rxb[2], rxb[3], rxb[4], rxb[5], rxb[6], rxb[7],
                              rxb[8], rxb[9], rxb[10], rxb[11], rxb[12], rxb[13], rxb[14], rxb[15]);
                end
                2: begin
                    #(1.0 * f[1]);
                    $fdisplay(fout, "2 %0d", longint'($realtime));
                end
                3: begin
                    t0 = $realtime;
                    if (f[1] == 2) begin
                        found0 = n_fall[0]; found1 = n_fall[1];
                        while ((n_fall[0] == found0 || n_fall[1] == found1) && $realtime - t0 < 1.0 * f[3]) @(posedge MCLK or negedge MCLK);
                        ta = (n_fall[0] != found0) ? longint'(t_fall[0] * 1000.0) : -1;
                        tb = (n_fall[1] != found1) ? longint'(t_fall[1] * 1000.0) : -1;
                        @(negedge MCLK);
                        $fdisplay(fout, "3 %0d %0d %0d", longint'($realtime), ta, tb);
                    end else if (f[1] == 3) begin
                        while (DRDY_N0 !== 1'b0 && DRDY_N1 !== 1'b0 && $realtime - t0 < 1.0 * f[3]) @(posedge MCLK or negedge MCLK);
                        @(negedge MCLK);
                        $fdisplay(fout, "3 %0d %0d %0d", longint'($realtime), DRDY_N0, DRDY_N1);
                    end else if (f[2] == 0) begin
                        while ((f[1] == 0 ? DRDY_N0 : DRDY_N1) !== 1'b0 && $realtime - t0 < 1.0 * f[3]) @(posedge MCLK or negedge MCLK);
                        @(negedge MCLK);
                        $fdisplay(fout, "3 %0d %0d %0d", longint'($realtime), (f[1] == 0 ? DRDY_N0 : DRDY_N1) === 1'b0,
                                  longint'(t_fall[f[1]] * 1000.0));
                    end else begin
                        found0 = n_fall[f[1]];
                        while (n_fall[f[1]] == found0 && $realtime - t0 < 1.0 * f[3]) @(posedge MCLK or negedge MCLK);
                        @(negedge MCLK);
                        $fdisplay(fout, "3 %0d %0d %0d", longint'($realtime), n_fall[f[1]] != found0,
                                  longint'(t_fall[f[1]] * 1000.0));
                    end
                end
                4: $fdisplay(fout, "4 %0d %0d %0d", longint'($realtime), DRDY_N0, DRDY_N1);
                5: begin
                    @(negedge MCLK);
                    #1;
                    RESET_N = f[1][0];
                    $fdisplay(fout, "5 %0d", longint'($realtime));
                end
                6: begin
                    v_off_uv[f[1]] = 1.0 * f[2];
                    sine_uv = 1.0 * f[3];
                    sine_hz = f[4] / 1000.0;
                    noise_uv[f[1]] = 1.0 * f[5];
                    $fdisplay(fout, "6 %0d", longint'($realtime));
                end
                7: begin
                    if (f[1] == 0)
                        $fdisplay(fout, "7 %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d", longint'($realtime),
                                  dut0.seq_state, dut0.seq_cnt, dut0.fifo_level, dut0.u_regs.err, dut0.u_regs.dflag_byte,
                                  dut0.u_regs.r_crc, dut0.u_regs.cfg_gen, dac_steps(OFM0, OFS0, OFEN0),
                                  OFEN0, AFE_RST0, longint'(resid_uv[0]), n_contention, n_frames);
                    else
                        $fdisplay(fout, "7 %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d", longint'($realtime),
                                  dut1.seq_state, dut1.seq_cnt, dut1.fifo_level, dut1.u_regs.err, dut1.u_regs.dflag_byte,
                                  dut1.u_regs.r_crc, dut1.u_regs.cfg_gen, dac_steps(OFM1, OFS1, OFEN1),
                                  OFEN1, AFE_RST1, longint'(resid_uv[1]), n_contention, n_frames);
                end
                8: begin
                    t_high = 1.0 * f[1]; t_low = 1.0 * f[2]; t_css = 1.0 * f[3]; t_csh = 1.0 * f[4]; t_idle = 1.0 * f[5];
                    $fdisplay(fout, "8 %0d", longint'($realtime));
                end
                9: begin
                    $fdisplay(fout, "9 %0d %0d", longint'($realtime), n_contention);
                    $fflush(fout);
                    $finish;
                end
                default: $fdisplay(fout, "0 %0d unknown op %0d (%0d fields)", longint'($realtime), f[0], nf);
            endcase
            $fflush(fout);
        end
    end
endmodule

`default_nettype wire
