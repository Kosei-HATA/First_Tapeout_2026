// eeg_spi_slave - SPI slave, mode 0 (CPOL = 0, CPHA = 0), MSB first.
//
// SCLK, CS_N and MOSI are asynchronous to MCLK. Each goes through a 2-FF
// synchronizer; SCLK and CS_N get one more register for edge detection. MOSI
// is synchronized with the same depth as SCLK, so at a detected SCLK rising
// edge the synchronized MOSI is the value present at that SCLK edge.
// MOSI is sampled on SCLK rising edges, MISO is updated after SCLK falling
// edges (latency 2..3 MCLK cycles after the pad edge, ~92 ns max).
//
// Transactions (CS_N low ... CS_N high), byte 0 = command:
//   0x30 READ_SAMPLE, 8 bytes. When the command byte completes the FIFO word
//        (head entry, or the empty word) is copied to a shadow register, so the
//        frame is consistent even if the FIFO changes meanwhile.
//        MISO: [0] 0x00, [1] STATUS, [2..3] SEQ (MSB first), [4..6] DATA
//        (MSB first), [7] CRC-8 over bytes 1..6 (poly 0x07, init 0x00, no
//        reflection, xorout 0x00).
//        The head entry is consumed (smp_pop) on CS_N rising only if exactly
//        8 complete bytes were transferred and the shadow held a valid entry.
//   0x10 READ_REG: bytes cmd, addr, dummy; MISO byte 2 = register value.
//   0x20 WRITE_REG: bytes cmd, addr, value; committed on CS_N rising only if
//        exactly 3 complete bytes were transferred.
//   other: cmd_err pulse when the command byte completes; MISO stays 0.
// MISO is 0 during the command byte and after the defined bytes.
//
// MISO_OE = ~CS_N (pad, unsynchronized) AND synchronized CS active:
//   * it turns on 1..2 MCLK cycles after CS_N falls (synchronized), and
//   * it turns off immediately (combinational path) when CS_N rises or when
//     the reset is asserted, as required for a shared MISO line.
//   Only one input of the AND changes at a time, so it does not glitch.
`timescale 1ns / 1ps
`default_nettype none

module eeg_spi_slave (
    input  logic        clk,
    input  logic        rst_n,
    // pads (asynchronous)
    input  logic        sclk,
    input  logic        cs_n,
    input  logic        mosi,
    output logic        miso,
    output logic        miso_oe,
    // register file
    output logic [7:0]  reg_addr,
    input  logic [7:0]  reg_rdata,
    output logic        reg_we,
    output logic [7:0]  reg_wdata,
    // sample FIFO
    input  logic [47:0] smp_word,          // {status, seq, data}; status[7] = VALID
    output logic        smp_pop,
    // error event
    output logic        cmd_err             // one-cycle pulse
);

    localparam logic [7:0] CMD_READ_REG    = 8'h10;
    localparam logic [7:0] CMD_WRITE_REG   = 8'h20;
    localparam logic [7:0] CMD_READ_SAMPLE = 8'h30;

    // ------------------------------------------------------------------
    // Synchronizers and edge detection
    // ------------------------------------------------------------------
    logic [2:0] sclk_q;                     // [0],[1] synchronizer, [2] edge detect
    logic [2:0] cs_q;
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

    logic cs_act;                           // synchronized chip select, active high
    logic cs_start;                         // CS_N falling edge
    logic cs_end;                           // CS_N rising edge
    logic sclk_rise;
    logic sclk_fall;
    logic mosi_s;

    assign cs_act    = ~cs_q[1];
    assign cs_start  = ~cs_q[1] &  cs_q[2];
    assign cs_end    =  cs_q[1] & ~cs_q[2];
    assign sclk_rise = cs_act &  sclk_q[1] & ~sclk_q[2];
    assign sclk_fall = cs_act & ~sclk_q[1] &  sclk_q[2];
    assign mosi_s    = mosi_q[1];

    assign miso_oe = ~cs_n & cs_act;

    // ------------------------------------------------------------------
    // Transaction state
    // ------------------------------------------------------------------
    logic [2:0]  bit_cnt;                   // bits received in the current byte
    logic [3:0]  byte_cnt;                  // complete bytes received (saturates at 15)
    logic [6:0]  rx_sh;                     // first 7 bits of the current byte
    logic [7:0]  rx_byte;
    logic [7:0]  cmd;                       // command of this transaction (0 until known)
    logic [47:0] shadow;                    // READ_SAMPLE frame {status, seq, data}
    logic [7:0]  tx_sh;                     // MISO shift register
    logic [7:0]  tx_next;                   // byte to send next

    assign rx_byte = {rx_sh, mosi_s};
    assign miso    = tx_sh[7];

    // CRC-8, polynomial x^8 + x^2 + x + 1 (0x07), init 0, MSB first, no
    // reflection, no final xor (CRC-8/SMBUS; check("123456789") = 0xF4).
    function automatic logic [7:0] crc8_48(input logic [47:0] d);
        logic [7:0] c;
        c = 8'h00;
        for (int i = 47; i >= 0; i = i - 1) begin
            if (c[7] ^ d[i]) begin
                c = {c[6:0], 1'b0} ^ 8'h07;
            end else begin
                c = {c[6:0], 1'b0};
            end
        end
        crc8_48 = c;
    endfunction

    // MISO bytes of a READ_SAMPLE frame
    logic [7:0] f_status, f_seq_h, f_seq_l, f_data_h, f_data_m, f_data_l, f_crc;

    assign f_status = shadow[47:40];
    assign f_seq_h  = shadow[39:32];
    assign f_seq_l  = shadow[31:24];
    assign f_data_h = shadow[23:16];
    assign f_data_m = shadow[15:8];
    assign f_data_l = shadow[7:0];
    assign f_crc    = crc8_48(shadow);            // CRC over bytes 1..6

    // Byte to load into tx_sh at the falling edge that starts byte number byte_cnt.
    always_comb begin
        tx_next = 8'h00;
        if (cmd == CMD_READ_SAMPLE) begin
            case (byte_cnt)
                4'd1:    tx_next = f_status;
                4'd2:    tx_next = f_seq_h;
                4'd3:    tx_next = f_seq_l;
                4'd4:    tx_next = f_data_h;
                4'd5:    tx_next = f_data_m;
                4'd6:    tx_next = f_data_l;
                4'd7:    tx_next = f_crc;
                default: tx_next = 8'h00;
            endcase
        end else if ((cmd == CMD_READ_REG) && (byte_cnt == 4'd2)) begin
            tx_next = reg_rdata;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bit_cnt   <= 3'd0;
            byte_cnt  <= 4'd0;
            rx_sh     <= 7'd0;
            cmd       <= 8'h00;
            reg_addr  <= 8'h00;
            reg_wdata <= 8'h00;
            shadow    <= 48'h0;
            tx_sh     <= 8'h00;
            reg_we    <= 1'b0;
            smp_pop   <= 1'b0;
            cmd_err   <= 1'b0;
        end else begin
            reg_we  <= 1'b0;
            smp_pop <= 1'b0;
            cmd_err <= 1'b0;

            if (cs_start) begin
                bit_cnt  <= 3'd0;
                byte_cnt <= 4'd0;
                cmd      <= 8'h00;
                tx_sh    <= 8'h00;
            end else if (cs_end) begin
                // commit only complete, exact-length transactions
                if (bit_cnt == 3'd0) begin
                    if ((cmd == CMD_WRITE_REG) && (byte_cnt == 4'd3)) begin
                        reg_we <= 1'b1;
                    end
                    if ((cmd == CMD_READ_SAMPLE) && (byte_cnt == 4'd8) && shadow[47]) begin
                        smp_pop <= 1'b1;
                    end
                end
                tx_sh <= 8'h00;
            end else begin
                if (sclk_rise) begin
                    bit_cnt <= bit_cnt + 3'd1;
                    if (bit_cnt == 3'd7) begin
                        // a byte is complete
                        if (byte_cnt != 4'd15) begin
                            byte_cnt <= byte_cnt + 4'd1;
                        end
                        case (byte_cnt)
                            4'd0: begin
                                cmd <= rx_byte;
                                if (rx_byte == CMD_READ_SAMPLE) begin
                                    shadow <= smp_word;
                                end else if ((rx_byte != CMD_READ_REG) && (rx_byte != CMD_WRITE_REG)) begin
                                    cmd_err <= 1'b1;
                                end
                            end
                            4'd1:    reg_addr  <= rx_byte;
                            4'd2:    reg_wdata <= rx_byte;
                            default: ;
                        endcase
                    end else begin
                        rx_sh <= rx_byte[6:0];
                    end
                end
                if (sclk_fall) begin
                    if (bit_cnt == 3'd0) begin
                        tx_sh <= tx_next;               // first bit of the next byte
                    end else begin
                        tx_sh <= {tx_sh[6:0], 1'b0};
                    end
                end
            end
        end
    end

endmodule

`default_nettype wire
