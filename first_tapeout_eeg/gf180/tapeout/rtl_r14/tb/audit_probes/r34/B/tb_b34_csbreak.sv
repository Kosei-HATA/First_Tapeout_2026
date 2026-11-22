// tb_b34_csbreak - audit round 34 (B): one CS_N glitch (a 3-MCLK High, 40 ns into the SCLK low phase before host pulse
// k) during a 3-byte CRC read [hdr, 0x00, 0x00]. The chip ends frame 1 there and starts frame 2 at pulse k (STATUS
// reloaded on MISO, frame 2's header taken from the host's remaining MOSI bits). For every k the host's 24-bit view is
// compared with the model of probes_b34/a34B_csbreak2.py: frame-1 MISO bits 0..k-1, then frame-2 MISO from its start,
// using the chip's own STATUS at each frame start and the bytes it loaded. Then one case of the window path: an ERR read
// broken before pulse 5 makes the chip decode 0xC0 (a short sample read); with the head sample's SEQ_H set to the value
// the model gives, the host's CRC check passes on a bogus ERR value.
`timescale 1ns / 1ps
`default_nettype none
module tb_b34_csbreak;
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
    logic ovl_on = 1'b0;                              // an overload (code 31) for OVL_NOW in the demonstration
    always @(posedge MCLK) CODE <= ovl_on ? 5'd31 : 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"
    // per frame: STATUS at each frame start and the bytes loaded onto MISO after each header
    integer nfr; logic [7:0] stf [0:3]; logic [7:0] ld [0:3][0:3]; integer nld [0:3];
    integer n_ferr = 0, n_pop = 0, n_snap = 0;
    always @(posedge MCLK) begin
        if (dut.u_spi.cs_start) begin
            nfr = nfr + 1; stf[nfr] = dut.status_byte; nld[nfr] = 0;
        end
        if (dut.u_spi.sclk_fall && dut.u_spi.bit_cnt == 3'd0 && !dut.u_spi.cs_start && !dut.u_spi.cs_end && nfr >= 0) begin
            ld[nfr][nld[nfr]] = dut.u_spi.tx_next; nld[nfr] = nld[nfr] + 1;
        end
        if (dut.frame_err) n_ferr++;
        if (dut.u_fifo.pop_ok) n_pop++;
        if (dut.smp_snap) n_snap++;
    end
    task automatic xfer_break(input logic [23:0] tx, input integer k, output logic [23:0] rx);
        CS_N = 1'b0;
        MOSI = tx[23];
        #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            SCLK = 1'b1; rx[23 - n] = miso_pad; #(spi_high);
            SCLK = 1'b0;
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 == k) begin                     // the glitch before pulse k
                #40.0; CS_N = 1'b1; #(3.0 * TMCLK); CS_N = 1'b0; #(spi_low - 40.0 - 3.0 * TMCLK);
            end else if (n + 1 < 24) #(spi_low);
        end
        #(spi_tcsh);
        CS_N = 1'b1;
        #(spi_tidle);
    endtask
    function automatic logic [7:0] c8(input logic [7:0] a, input logic [7:0] b);
        return tb_crc8_update(tb_crc8_update(8'h00, a), b);
    endfunction
    integer nbad = 0, ncmp = 0, nhaz = 0;
    task automatic one(input logic [6:0] addr, input integer k, input bit show, input bit clear = 1'b1);
        logic [23:0] rx, f1, f2, pred, top;
        logic [7:0] h, v, d, c;
        h = {1'b1, addr};
        nfr = -1;
        xfer_break({h, 16'h0000}, k, rx);
        v = (nld[0] > 0) ? ld[0][0] : 8'h00;
        f1 = {stf[0], v, c8(h, v)};
        f2 = {stf[1], (nld[1] > 0) ? ld[1][0] : 8'h00, (nld[1] > 1) ? ld[1][1] : 8'h00};
        top = ~(24'hFFFFFF >> k);
        pred = (f1 & top) | (f2 >> k);
        ncmp++;
        d = rx[15:8]; c = rx[7:0];
        if (rx !== pred) begin
            nbad++;
            if (nbad <= 10) $display("MISMATCH addr %02h k %0d: host %06h, model %06h (STATUS %02h / %02h, loads1 %0d loads2 %0d)", addr, k, rx, pred, stf[0], stf[1], nld[0], nld[1]);
        end
        if (rx[23:22] == 2'b10 && c == c8(h, d) && d != v) begin
            nhaz++;
            $display("CRC-valid misread: addr %02h break before pulse %0d: host %06h reads %02h (chip value %02h), frame 2 STATUS %02h loads %02h %02h", addr, k, rx, d, v, stf[1], ld[1][0], ld[1][1]);
        end
        if (show) $display("addr %02h k %0d: host %06h model %06h", addr, k, rx, pred);
        if (clear) r14_write(7'h06, 8'hFE);           // clear what the broken frames set (CRC on)
    endtask
    logic [7:0] st, vv;
    logic [15:0] sq;
    logic [23:0] dt;
    bit ok;
    integer p0, s0, f0;
    initial begin
        spi_high = 500.0; spi_low = 500.0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h09, 8'h00);
        r14_cmd(CMD_START);
        do r14_read(7'h04, vv); while (vv != ST_RUN);
        while (DRDY_N !== 1'b0) @(posedge MCLK);       // a sample waits in the FIFO (not read)
        // 1) the model of the host view against the RTL, every break position, for STATE, ERR, IF_CFG, FIFO_LEVEL, DFLAG
        for (int k = 2; k < 24; k++) begin
            one(7'h04, k, 0); one(7'h06, k, 0); one(7'h55, k, 0); one(7'h05, k, 0); one(7'h07, k, 0);
        end
        $display("model check: %0d broken reads, %0d host views differ from the model, %0d CRC-valid misreads", ncmp, nbad, nhaz);
        // 2) the window path of ERR (break before pulse 5 -> frame 2's header 0xC0, a short sample read): RUN with a
        //    sample waiting, an overload (OVL_NOW), ALERT from an uncleared FRAME_ERR, and the waiting head sample with
        //    status 0x90 (VALID, CHANGED) and SEQ_H 0x60 (deposited): the model gives a CRC-valid ERR of 0x74
        ovl_on = 1'b1;
        repeat (40 * 32) @(posedge MCLK);              // 40 frames of code 31: OVL_NOW = 1
        one(7'h06, 3, 0, 0);                           // a broken read whose FRAME_ERR is left set: ALERT = 1
        dut.u_fifo.mem[dut.u_fifo.rd_ptr] = {8'h90, 16'h6000, 24'h012345};
        p0 = n_pop; s0 = n_snap; f0 = n_ferr;
        $display("before: STATUS %02h, ERR %02h, FIFO_LEVEL %0d, head %012h", dut.status_byte, dut.u_regs.err,
                 dut.fifo_level, dut.smp_word);
        one(7'h06, 5, 1, 0);
        $display("after: ERR %02h (the chip's), FIFO_LEVEL %0d; in the broken read: snaps %0d, pops %0d, FRAME_ERR pulses %0d",
                 dut.u_regs.err, dut.fifo_level, n_snap - s0, n_pop - p0, n_ferr - f0);
        ovl_on = 1'b0;
        $display("tb_b34_csbreak: %0d CRC-valid misreads in all; %0d host views differ from the model", nhaz, nbad);
        $finish;
    end
endmodule
`default_nettype wire
