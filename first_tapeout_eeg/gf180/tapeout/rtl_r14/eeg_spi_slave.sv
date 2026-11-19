// eeg_spi_slave - SPI slave of the digital control (r14), mode 0, MSB first.
//
// Specification: gf180/tapeout/rtl/spec/fsm_spec.py (SPI: states and transition table) and
// documentation/gf180_digital_control_spec_20261119.md section 3.
//   * byte 0 (MOSI): bit 7 = R/W (1 = read), bits 6:0 = address; during it MISO returns STATUS (copied at the
//     CS_N fall; bit 7 = 1, bit 6 = 0 fixed).
//   * write: header + data (+ CRC when crc_en), fixed length; committed at CS_N rising only when complete and the
//     CRC matches (CRC-8, poly 0x07, over the header and the data byte); otherwise FRAME_ERR / CRC_ERR, nothing
//     written. MISO 0x00 after the header.
//   * read: header + data bytes, the address incrementing (crc_en: header + one data byte + CRC over the header as
//     received and the data byte as sent). An undefined header address flags ADDR_ERR (data 0x00).
//   * sample: header address 0x40, then STATUS, SEQ (2), DATA (3), CRC (over those 6): the FIFO head is copied when
//     the header completes (smp_snap) and the pop is requested at CS_N rising only after exactly 8 bytes; the FIFO
//     removes the head only if the copy is still the head (eeg_fifo `held`).
//   * a bit after a completed fixed frame -> OVF (FRAME_ERR at CS_N rising); CS_N rising inside a byte -> FRAME_ERR;
//     with CRC on, a read that stops before its CRC byte or a sample read shorter than 8 bytes -> FRAME_ERR (a
//     header-only read, the status poll, stays legal); an empty frame (no SCLK) is no error.
// Synchronizers as in rtl/eeg_spi_slave.sv (MCLK oversampling, SCLK <= 2 MHz). MISO_OE = ~CS_N (pad) & the
// synchronized CS (turns on 1..2 MCLK after the fall, off at once at the rise).
`timescale 1ns / 1ps
`default_nettype none

module eeg_spi_slave (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        sclk,
    input  logic        cs_n,
    input  logic        mosi,
    output logic        miso,
    output logic        miso_oe,
    input  logic [7:0]  status_byte,
    output logic [6:0]  reg_addr,
    input  logic [7:0]  reg_rdata,
    input  logic        reg_addr_ok,
    output logic        reg_we,
    output logic [7:0]  reg_wdata,
    input  logic        crc_en,
    input  logic [47:0] smp_word,
    output logic        smp_snap,
    output logic        smp_pop,
    output logic        frame_err,
    output logic        crc_err,
    output logic        addr_err
);

`include "eeg_regs_defs.svh"

    localparam logic [3:0] S_IDLE = 4'd0, S_HDR = 4'd1, S_RREG = 4'd2, S_RCRC = 4'd3, S_RDONE = 4'd4,
                           S_RSMP = 4'd5, S_SDONE = 4'd6, S_WDAT = 4'd7, S_WCRC = 4'd8, S_WDONE = 4'd9,
                           S_OVF = 4'd10;

    // ---------------- synchronizers and edges (as rtl/eeg_spi_slave.sv)
    logic [2:0] sclk_q, cs_q;
    logic [1:0] mosi_q;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sclk_q <= 3'b000;
            cs_q   <= 3'b111;
            mosi_q <= 2'b00;
        end else begin
            sclk_q <= {sclk_q[1:0], sclk};
            cs_q   <= {cs_q[1:0], cs_n};
            mosi_q <= {mosi_q[0], mosi};
        end
    end
    logic cs_act, cs_start, cs_end, sclk_rise, sclk_fall, mosi_s;
    assign cs_act    = ~cs_q[1];
    assign cs_start  = ~cs_q[1] &  cs_q[2];
    assign cs_end    =  cs_q[1] & ~cs_q[2];
    assign sclk_rise = cs_act &  sclk_q[1] & ~sclk_q[2];
    assign sclk_fall = cs_act & ~sclk_q[1] &  sclk_q[2];
    assign mosi_s    = mosi_q[1];
    assign miso_oe   = ~cs_n & cs_act;

    // ---------------- CRC-8 (0x07, init 0, MSB first, no reflection, no final xor)
    function automatic logic [7:0] crc8_step(input logic [7:0] c, input logic [7:0] d);
        logic [7:0] x;
        x = c;
        for (int i = 7; i >= 0; i = i - 1) begin
            if (x[7] ^ d[i]) x = {x[6:0], 1'b0} ^ 8'h07;
            else             x = {x[6:0], 1'b0};
        end
        crc8_step = x;
    endfunction
    // A sample's CRC starts from its header 0xC0 (CRC_SMP_HDR = CRC-8 of 0xC0), like a register read's CRC, which
    // covers the received header. Over the six bytes alone, an all-zero response (a header turned into a write by a
    // bit error, or a MISO nobody drives) read as an empty word with a valid CRC (audit round 5, 11/20).
    localparam logic [7:0] CRC_SMP_HDR = 8'h4E;
    function automatic logic [7:0] crc8_48(input logic [7:0] c0, input logic [47:0] d);
        logic [7:0] c;
        c = c0;
        for (int b = 5; b >= 0; b = b - 1) c = crc8_step(c, d[8*b +: 8]);
        crc8_48 = c;
    endfunction

    // ---------------- transaction
    logic [3:0]  st;
    logic [2:0]  bit_cnt;
    logic [6:0]  rx_sh;
    logic [7:0]  rx_byte, tx_sh, tx_next, hdr, wdat, wcrc, txd;
    logic [47:0] shadow;
    logic [2:0]  k;
    logic        chk_addr;

    assign rx_byte   = {rx_sh, mosi_s};
    assign miso      = tx_sh[7];
    assign reg_wdata = wdat;

    always_comb begin
        case (st)
            S_RREG:  tx_next = reg_rdata;
            S_RCRC:  tx_next = crc8_step(crc8_step(8'h00, hdr), txd);
            S_RSMP: begin
                case (k)
                    3'd0:    tx_next = shadow[47:40];
                    3'd1:    tx_next = shadow[39:32];
                    3'd2:    tx_next = shadow[31:24];
                    3'd3:    tx_next = shadow[23:16];
                    3'd4:    tx_next = shadow[15:8];
                    3'd5:    tx_next = shadow[7:0];
                    default: tx_next = crc8_48(CRC_SMP_HDR, shadow);
                endcase
            end
            default: tx_next = 8'h00;
        endcase
    end

    logic done_st;
    assign done_st = (st == S_RDONE) || (st == S_SDONE) || (st == S_WDONE);

    // the cycle in which the header of a sample read completes and `shadow` copies smp_word (same conditions as the
    // copy below; combinational, so that the FIFO sees the copy in the cycle it is taken)
    assign smp_snap = !cs_start && !cs_end && sclk_rise && (st == S_HDR) && (bit_cnt == 3'd7) && rx_byte[7] &&
                      (rx_byte[6:0] == A_SAMPLE);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st        <= S_IDLE;
            bit_cnt   <= 3'd0;
            rx_sh     <= 7'd0;
            tx_sh     <= 8'h00;
            hdr       <= 8'h00;
            wdat      <= 8'h00;
            wcrc      <= 8'h00;
            txd       <= 8'h00;
            shadow    <= 48'h0;
            k         <= 3'd0;
            reg_addr  <= 7'd0;
            chk_addr  <= 1'b0;
            reg_we    <= 1'b0;
            smp_pop   <= 1'b0;
            frame_err <= 1'b0;
            crc_err   <= 1'b0;
            addr_err  <= 1'b0;
        end else begin
            reg_we    <= 1'b0;
            smp_pop   <= 1'b0;
            frame_err <= 1'b0;
            crc_err   <= 1'b0;
            addr_err  <= chk_addr && !reg_addr_ok;       // the read header's address, one cycle later
            chk_addr  <= 1'b0;
            if (cs_start) begin
                st      <= S_HDR;
                bit_cnt <= 3'd0;
                tx_sh   <= status_byte;                  // STATUS during the header byte
            end else if (cs_end) begin
                if (st != S_IDLE) begin
                    if (bit_cnt != 3'd0 || st == S_OVF || st == S_WDAT || st == S_WCRC ||
                        (crc_en && (st == S_RCRC || st == S_RSMP)) || st > S_OVF) begin
                        frame_err <= 1'b1;               // inside a byte, overlong, an incomplete write, (CRC on)
                                                         // a read without its CRC or a short sample, or an illegal
                                                         // state value (NFR-05: nothing committed, flagged)
                    end else if (st == S_WDONE) begin
                        if (crc_en && (wcrc != crc8_step(crc8_step(8'h00, hdr), wdat))) crc_err <= 1'b1;
                        else                                                            reg_we  <= 1'b1;
                    end else if (st == S_SDONE) begin
                        smp_pop <= 1'b1;                 // the FIFO pops only if the copy is still its head
                    end
                end
                st    <= S_IDLE;
                tx_sh <= 8'h00;
            end else begin
                if (sclk_rise) begin
                    bit_cnt <= bit_cnt + 3'd1;
                    if (bit_cnt != 3'd7) rx_sh <= rx_byte[6:0];
                    if (done_st) begin
                        st <= S_OVF;                     // a bit after a completed frame
                    end else if (bit_cnt == 3'd7) begin  // a byte is complete
                        case (st)
                            S_HDR: begin
                                hdr      <= rx_byte;
                                reg_addr <= rx_byte[6:0];
                                if (rx_byte[7]) begin
                                    if (rx_byte[6:0] == A_SAMPLE) begin
                                        shadow <= smp_word;
                                        k      <= 3'd0;
                                        st     <= S_RSMP;
                                    end else begin
                                        st       <= S_RREG;
                                        chk_addr <= 1'b1;
                                    end
                                end else begin
                                    st <= S_WDAT;
                                end
                            end
                            S_RREG: begin
                                if (crc_en) st <= S_RCRC;
                                else        reg_addr <= reg_addr + 7'd1;
                            end
                            S_RCRC: st <= S_RDONE;
                            S_RSMP: begin
                                if (k == 3'd6) st <= S_SDONE;
                                else           k  <= k + 3'd1;
                            end
                            S_WDAT: begin
                                wdat <= rx_byte;
                                st   <= crc_en ? S_WCRC : S_WDONE;
                            end
                            S_WCRC: begin
                                wcrc <= rx_byte;
                                st   <= S_WDONE;
                            end
                            default: ;                   // OVF: stays
                        endcase
                    end
                end
                if (sclk_fall) begin
                    if (bit_cnt == 3'd0) begin
                        tx_sh <= tx_next;                // first bit of the next byte
                        txd   <= tx_next;
                    end else begin
                        tx_sh <= {tx_sh[6:0], 1'b0};
                    end
                end
            end
        end
    end

endmodule

`default_nettype wire
