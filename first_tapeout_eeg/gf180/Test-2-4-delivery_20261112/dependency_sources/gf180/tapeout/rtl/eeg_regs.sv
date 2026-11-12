// eeg_regs - SPI-accessible control and status registers.
//
//  addr  name        access  reset  bits
//  0x00  ID          RO      0xE6
//  0x01  VERSION     RO      0x07
//  0x02  CONTROL     RW      0x74   0 RUN, 1 FILTER_CLEAR (self clearing, reads 0),
//                                   2 DWA_EN, 3 RAW_EN, 4 AFE_RST, 5 CHOP_EN,
//                                   6 CHOP_FAST (1 = 128 kHz, 0 = 64 kHz chop), 7 reads 0
//  0x03  STATUS      RO/W1C  -      0 FIFO_NONEMPTY (RO), 1 SETTLING (RO),
//                                   2 OVERRUN (W1C), 3 CMD_ERR (W1C), 7:4 read 0
//  0x04  FORMAT      RO      0x05   [3:0] quantizer bits = 5
//  0x05  FIFO_LEVEL  RO      -      0..8
//  0x06  ODR_H       RO      0x03   output data rate 1000 SPS = 0x03E8
//  0x07  ODR_L       RO      0xE8
//  0x08  CHOP_DLY    RW      0x00   chop_out delay in MCLK cycles
//  0x09  TEST        RW      0x00   routed to test_cfg[7:0]: [4] ATP enable, [3:0] node select,
//                                   [5] ADC_ZERO, [7:6] DBG_SEL (eeg_digital_top, eeg_raw)
//                                   (gf180/tapeout/test/eeg_testmux.spice), [7:5] unused
//  0x0A  ANA_TRIM    RW      0x28   [3:0] CPF_TRIM (reset 8), [5:4] AFE_IBIAS (reset 2),
//                                   7:6 read 0; plain outputs decoded by the analog side
//  0x0B  BLANK       RW      0x07   [3:0] BLANK_LEN: CHOP_BLANK width in MCLK (0 = off), 7:4 read 0
//  0x0C  BOOST_TRIM  RW      0x05   [1:0] BTRIM_P (reset 1), [3:2] BTRIM_N (reset 1), 7:4 read 0;
//                                   cascode-booster units 00 = 2, 01 = 4, 10 = 6, 11 = 8,
//                                   plain outputs decoded by the analog bias block
//  0x0D  OFF_CODE_L  RW      0x00   electrode-offset DAC magnitude M[7:0]
//  0x0E  OFF_CTRL    RW      0x00   [1:0] M[9:8], [3] SIGN, [6:4] OFF_RANGE (0 = off,
//                                   1..4 = +-39/79/159/318 mV, 5..7 = 4), 2 and 7 read 0;
//                                   the analog DAC cancels (1 - 2 SIGN) x M x 0.311 mV of
//                                   ELP-ELN offset, M limited by the range
//                                   (documentation/gf180_electrode_dc_20261022.md)
//  0x0F  CHOP1       RW      0x03   [2:0] CHOP1_RATE: OTA1 chopper 0 = off (phase A),
//                                   1..5 = 1/2/4/8/16 kHz, 6..7 = 16 kHz; 7:3 read 0;
//                                   applied at the next 1 ms boundary (eeg_chop1.sv)
//  other addresses read 0x00; writes to them and to RO registers are ignored.
//
// Sticky flags: a set event in the same cycle as a W1C clear wins, so no event
// is lost. FILTER_CLEAR produces a one-MCLK pulse on filter_clear.
`timescale 1ns / 1ps
`default_nettype none

module eeg_regs (
    input  logic       clk,
    input  logic       rst_n,
    // register port from the SPI slave
    input  logic [7:0] addr,           // address for reads and writes
    output logic [7:0] rdata,          // combinational read data
    input  logic       we,             // one-cycle write strobe
    input  logic [7:0] wdata,
    // status inputs
    input  logic       fifo_nonempty,
    input  logic       settling,
    input  logic [3:0] fifo_level,
    input  logic       ovr_set,        // pulse: FIFO overrun (sample dropped)
    input  logic       cmd_err_set,    // pulse: unknown SPI command
    // control outputs
    output logic       run,
    output logic       filter_clear,   // one-cycle pulse
    output logic       dwa_en,
    output logic       raw_en,
    output logic       afe_rst,
    output logic       chop_en,
    output logic       chop_fast,      // 1 = 128 kHz chop, 0 = 64 kHz
    output logic [7:0] chop_dly,
    output logic [7:0] test_cfg,
    output logic [3:0] cpf_trim,       // ANA_TRIM[3:0]
    output logic [1:0] afe_ibias,      // ANA_TRIM[5:4]
    output logic [3:0] blank_len,      // BLANK[3:0]
    output logic [1:0] btrim_p,        // BOOST_TRIM[1:0]: PMOS-cascode booster units
    output logic [1:0] btrim_n,        // BOOST_TRIM[3:2]: NMOS-cascode booster units
    output logic [9:0] off_mag,        // OFF_CTRL[1:0], OFF_CODE_L: offset-DAC magnitude
    output logic       off_sign,       // OFF_CTRL[3]: offset-DAC sign
    output logic [2:0] off_range,      // OFF_CTRL[6:4]: offset-DAC range (0 = off)
    output logic [2:0] chop1_rate,     // CHOP1[2:0]: OTA1 chopper rate
    output logic       ovr_flag,       // sticky OVERRUN
    output logic       cmd_err_flag    // sticky CMD_ERR
);

    localparam logic [7:0] A_ID         = 8'h00;
    localparam logic [7:0] A_VERSION    = 8'h01;
    localparam logic [7:0] A_CONTROL    = 8'h02;
    localparam logic [7:0] A_STATUS     = 8'h03;
    localparam logic [7:0] A_FORMAT     = 8'h04;
    localparam logic [7:0] A_FIFO_LEVEL = 8'h05;
    localparam logic [7:0] A_ODR_H      = 8'h06;
    localparam logic [7:0] A_ODR_L      = 8'h07;
    localparam logic [7:0] A_CHOP_DLY   = 8'h08;
    localparam logic [7:0] A_TEST       = 8'h09;
    localparam logic [7:0] A_ANA_TRIM   = 8'h0A;
    localparam logic [7:0] A_BLANK      = 8'h0B;
    localparam logic [7:0] A_BOOST_TRIM = 8'h0C;
    localparam logic [7:0] A_OFF_CODE_L = 8'h0D;
    localparam logic [7:0] A_OFF_CTRL   = 8'h0E;
    localparam logic [7:0] A_CHOP1      = 8'h0F;

    localparam logic [7:0] ID_VALUE      = 8'hE6;
    localparam logic [7:0] VERSION_VALUE = 8'h07;
    localparam logic [7:0] FORMAT_VALUE  = 8'h05;   // 5-bit quantizer
    localparam logic [15:0] ODR_VALUE    = 16'd1000;

    logic status_w1c;

    assign status_w1c = we && (addr == A_STATUS);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            run          <= 1'b0;
            filter_clear <= 1'b0;
            dwa_en       <= 1'b1;
            raw_en       <= 1'b0;
            afe_rst      <= 1'b1;
            chop_en      <= 1'b1;
            chop_fast    <= 1'b1;
            chop_dly     <= 8'h00;
            test_cfg     <= 8'h00;
            cpf_trim     <= 4'd8;
            afe_ibias    <= 2'd2;
            blank_len    <= 4'd7;
            btrim_p      <= 2'd1;
            btrim_n      <= 2'd1;
            off_mag      <= 10'h000;
            off_sign     <= 1'b0;
            off_range    <= 3'd0;
            chop1_rate   <= 3'd3;
            ovr_flag     <= 1'b0;
            cmd_err_flag <= 1'b0;
        end else begin
            filter_clear <= 1'b0;
            if (we) begin
                case (addr)
                    A_CONTROL: begin
                        run          <= wdata[0];
                        filter_clear <= wdata[1];
                        dwa_en       <= wdata[2];
                        raw_en       <= wdata[3];
                        afe_rst      <= wdata[4];
                        chop_en      <= wdata[5];
                        chop_fast    <= wdata[6];
                    end
                    A_CHOP_DLY: chop_dly <= wdata;
                    A_TEST:     test_cfg <= wdata;
                    A_ANA_TRIM: begin
                        cpf_trim  <= wdata[3:0];
                        afe_ibias <= wdata[5:4];
                    end
                    A_BLANK:    blank_len <= wdata[3:0];
                    A_BOOST_TRIM: begin
                        btrim_p <= wdata[1:0];
                        btrim_n <= wdata[3:2];
                    end
                    A_OFF_CODE_L: off_mag[7:0] <= wdata;
                    A_OFF_CTRL: begin
                        off_mag[9:8] <= wdata[1:0];
                        off_sign     <= wdata[3];
                        off_range    <= wdata[6:4];
                    end
                    A_CHOP1:    chop1_rate <= wdata[2:0];
                    default:    ;
                endcase
            end

            if (ovr_set) begin
                ovr_flag <= 1'b1;
            end else if (status_w1c && wdata[2]) begin
                ovr_flag <= 1'b0;
            end

            if (cmd_err_set) begin
                cmd_err_flag <= 1'b1;
            end else if (status_w1c && wdata[3]) begin
                cmd_err_flag <= 1'b0;
            end
        end
    end

    always_comb begin
        case (addr)
            A_ID:         rdata = ID_VALUE;
            A_VERSION:    rdata = VERSION_VALUE;
            A_CONTROL:    rdata = {1'b0, chop_fast, chop_en, afe_rst, raw_en, dwa_en, 1'b0, run};
            A_STATUS:     rdata = {4'b0000, cmd_err_flag, ovr_flag, settling, fifo_nonempty};
            A_FORMAT:     rdata = FORMAT_VALUE;
            A_FIFO_LEVEL: rdata = {4'b0000, fifo_level};
            A_ODR_H:      rdata = ODR_VALUE[15:8];
            A_ODR_L:      rdata = ODR_VALUE[7:0];
            A_CHOP_DLY:   rdata = chop_dly;
            A_TEST:       rdata = test_cfg;
            A_ANA_TRIM:   rdata = {2'b00, afe_ibias, cpf_trim};
            A_BLANK:      rdata = {4'b0000, blank_len};
            A_BOOST_TRIM: rdata = {4'b0000, btrim_n, btrim_p};
            A_OFF_CODE_L: rdata = off_mag[7:0];
            A_OFF_CTRL:   rdata = {1'b0, off_range, off_sign, 1'b0, off_mag[9:8]};
            A_CHOP1:      rdata = {5'b00000, chop1_rate};
            default:      rdata = 8'h00;
        endcase
    end

endmodule

`default_nettype wire
