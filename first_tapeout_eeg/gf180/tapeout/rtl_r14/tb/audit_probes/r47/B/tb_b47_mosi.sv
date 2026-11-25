// tb_b47_mosi - audit round 47, auditor B probe (not part of the repository's benches).
// Every single MOSI bit flip of every CRC-on frame kind the host procedure sends, in RUN with samples in the FIFO:
// 3-byte reads of every address the procedure reads, the header-only STATUS poll, 8-byte sample reads, 3-byte writes
// (COMMAND FLUSH, OFF_M_L, ERR W1C, TEST_KEY lock, T_ELEC, IF_CFG). Per frame the host's acceptance rule (requirements
// 5.4 rule (a), (b), step 6) is applied to what it received and compared with what the chip actually did (backdoor):
//   read accepted (fixed bits, CRC over the intended header) while the chip decoded another header  -> BAD
//   sample accepted (sample CRC) while the chip did not copy the head, or VALID and not popped without FRAME_ERR -> BAD
//   write passes rule (a) (fixed bits, MISO 0x00 after the header) while the chip committed something else, or nothing
//     and raised no ERR flag -> BAD
`timescale 1ns / 1ps
`default_nettype none
module tb_b47_mosi;
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
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"

    // what the chip did during a frame
    integer n_we, n_wok, n_snap, n_pop, n_ferr, n_cerr, n_aerr;
    logic [7:0] we_ev; logic [6:0] we_a; logic [7:0] we_d;
    always @(negedge CS_N) begin n_we = 0; n_wok = 0; n_snap = 0; n_pop = 0; n_ferr = 0; n_cerr = 0; n_aerr = 0; we_ev = 0; end
    always @(posedge MCLK) begin
        if (dut.reg_we) begin n_we++; we_a = dut.reg_addr; we_d = dut.reg_wdata; we_ev = dut.u_regs.ev_err;
                              if (dut.u_regs.w_ok) n_wok++; end
        if (dut.smp_snap) n_snap++;
        if (dut.u_fifo.pop_ok) n_pop++;
        if (dut.frame_err) n_ferr++;
        if (dut.crc_err) n_cerr++;
        if (dut.addr_err) n_aerr++;
    end
    integer n_bad = 0, n_frames = 0, n_acc = 0, n_rej = 0, n_flagged = 0, n_silent_ok = 0;
    task automatic bad(input string s); n_bad++; if (n_bad <= 40) $display("BAD: %s", s); endtask
    function automatic logic [7:0] crc(input logic [7:0] c0, input logic [7:0] d); return tb_crc8_update(c0, d); endfunction

    task automatic xfer_flip(input integer nbytes, input integer fb);
        if (fb >= 0) spi_tx[fb / 8][7 - fb % 8] = ~spi_tx[fb / 8][7 - fb % 8];
        spi_xfer(nbytes, 0);
        repeat (8) @(posedge MCLK);
        n_frames++;
    endtask

    task automatic clear_err();   // backdoor-free: W1C every flag with a clean CRC write
        logic [7:0] v;
        r14_read(7'h06, v); r14_write(7'h06, v);
    endtask

    logic [7:0] hdr_dec, v, h;
    logic [47:0] head;
    integer lvl0;
    bit acc;
    initial begin
        logic [7:0] addrs [0:38];
        logic [7:0] ai;
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;                     // CRC on
        r14_write(7'h21, 8'hAA); r14_write(7'h22, 8'h02); r14_write(7'h24, 8'h05); r14_write(7'h50, 8'd6);
        r14_write(7'h52, 8'd29); r14_write(7'h09, 8'h00);
        r14_write(7'h10, 8'h11);                                        // START
        wait (dut.seq_state == ST_RUN); repeat (3 * 32768) @(posedge MCLK); // 3 samples in the FIFO
        clear_err();
        addrs = '{8'h00, 8'h01, 8'h02, 8'h03, 8'h04, 8'h05, 8'h06, 8'h07, 8'h08, 8'h09, 8'h20, 8'h21, 8'h22, 8'h23,
                  8'h24, 8'h25, 8'h26, 8'h27, 8'h28, 8'h30, 8'h31, 8'h32, 8'h33, 8'h34, 8'h35, 8'h36, 8'h37, 8'h38,
                  8'h50, 8'h51, 8'h52, 8'h53, 8'h54, 8'h55, 8'h60, 8'h61, 8'h62, 8'h70, 8'h71};
        // ---- 3-byte CRC reads, every flip of the 24 bits
        for (int i = 0; i < 39; i++) for (int fb = 0; fb < 24; fb++) begin
            ai = addrs[i];
            h = 8'h80 | ai;
            spi_tx[0] = h; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
            xfer_flip(3, fb);
            hdr_dec = dut.u_spi.hdr;
            acc = (spi_rx[0][7:6] == 2'b10) && (spi_rx[2] == crc(crc(8'h00, h), spi_rx[1]));
            if (acc) n_acc++; else n_rej++;
            if (acc && hdr_dec != h)
                bad($sformatf("read 0x%02h flip %0d: accepted 0x%02h, chip decoded header 0x%02h", h, fb, spi_rx[1], hdr_dec));
            if (n_ferr || n_cerr || n_aerr || we_ev) begin n_flagged++; clear_err(); end
        end
        // ---- header-only STATUS poll
        for (int fb = 0; fb < 8; fb++) begin
            spi_tx[0] = 8'h83; xfer_flip(1, fb);
            $display("poll flip %0d: header 0x%02h -> ferr %0d aerr %0d ev %02h", fb, dut.u_spi.hdr, n_ferr, n_aerr, we_ev);
            if (n_ferr || n_cerr || n_aerr || we_ev) begin n_flagged++; clear_err(); end
        end
        // ---- 8-byte sample reads, every flip of the 64 bits
        for (int fb = 0; fb < 64; fb++) begin
            logic [7:0] cc;
            if (dut.fifo_level < 2) repeat (2 * 32768) @(posedge MCLK);
            lvl0 = dut.fifo_level; head = dut.smp_word;
            spi_tx[0] = SMP_HDR; for (int b = 1; b < 8; b++) spi_tx[b] = 8'h00;
            xfer_flip(8, fb);
            cc = crc(8'h00, SMP_HDR); for (int b = 1; b < 7; b++) cc = crc(cc, spi_rx[b]);
            acc = (cc == spi_rx[7]);
            if (acc) n_acc++; else n_rej++;
            if (acc && n_snap != 1) bad($sformatf("sample flip %0d: accepted a word the chip did not copy", fb));
            if (acc && spi_rx[1][7] && n_pop != 1 && n_ferr == 0)
                bad($sformatf("sample flip %0d: VALID word accepted, not popped, no FRAME_ERR", fb));
            if (acc && {spi_rx[1], spi_rx[2], spi_rx[3], spi_rx[4], spi_rx[5], spi_rx[6]} !== head)
                bad($sformatf("sample flip %0d: accepted word differs from the head", fb));
            if (n_ferr || n_cerr || n_aerr || we_ev) begin n_flagged++; clear_err(); end
        end
        // ---- 3-byte CRC writes, every flip of the 24 bits
        begin
            logic [7:0] wa [0:5]; logic [7:0] wd [0:5];
            wa = '{8'h10, 8'h21, 8'h06, 8'h11, 8'h51, 8'h55}; wd = '{8'h55, 8'hAB, 8'h00, 8'h00, 8'h02, 8'h01};
            for (int k = 0; k < 6; k++) for (int fb = 0; fb < 24; fb++) begin
                spi_tx[0] = wa[k]; spi_tx[1] = wd[k]; spi_tx[2] = crc(crc(8'h00, wa[k]), wd[k]);
                xfer_flip(3, fb);
                acc = (spi_rx[0][7:6] == 2'b10) && spi_rx[1] == 8'h00 && spi_rx[2] == 8'h00;
                if (acc) n_acc++; else n_rej++;
                if (n_wok && !(we_a == wa[k][6:0] && we_d == wd[k]))
                    bad($sformatf("write %02h<-%02h flip %0d: committed %02h<-%02h", wa[k], wd[k], fb, we_a, we_d));
                if (acc && n_wok == 0 && we_ev == 0 && n_ferr == 0 && n_cerr == 0 && n_aerr == 0)
                    bad($sformatf("write %02h<-%02h flip %0d: rule (a) passes, nothing committed, no flag", wa[k], wd[k], fb));
                if (acc && n_wok && we_a == wa[k][6:0] && we_d == wd[k]) n_silent_ok++;
                if (n_ferr || n_cerr || n_aerr || we_ev) begin n_flagged++; clear_err(); end
                if (bfm_crc_en !== dut.crc_en) begin $display("CRC mode changed at write %0d flip %0d", k, fb); bfm_crc_en = dut.crc_en; end
            end
        end
        $display("tb_b47_mosi: %0d faulted frames, accepted %0d, rejected %0d, flagged %0d, intended-commit-despite-flip %0d, BAD %0d, SPI errors %0d",
                 n_frames, n_acc, n_rej, n_flagged, n_silent_ok, n_bad, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
