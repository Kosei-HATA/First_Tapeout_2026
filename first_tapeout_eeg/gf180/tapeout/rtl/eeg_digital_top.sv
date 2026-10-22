// eeg_digital_top - digital block of the GF180 EEG ADC (single channel).
//
// Single clock domain: MCLK = 32.768 MHz from an external oscillator.
// One modulator frame = 32 MCLK cycles (fs = 1.024 MHz). See README.md for the
// frame timing diagram, register map and SPI frame format.
//
// Data path per frame (e_n = rising MCLK edge that starts frame cycle n):
//   e0  CMP_STROBE rises; the quantizer compares and latches its decision.
//   e2  TH[30:0] is captured into th_q (th_capture = cycle 1).
//       code = popcount(th_q), k = 31 - code
//   e3  SEL1/SEL2 update from k (dac_load = cycle DAC_LOAD_CYCLE = 2).
//       Excess loop delay CMP_STROBE -> SEL = (DAC_LOAD_CYCLE + 1) MCLK = 91.6 ns.
//   e4  CIC integrators take x = 2*code - 31 (cic_en = cycle 3).
//
// TH timing assumption (no synchronizer on TH): TH is driven by the analog
// quantizer in response to CMP_STROBE, i.e. it is launched by the e0 edge of
// this same clock. It must be settled at e2 (two MCLK periods after the strobe
// edge, minus clock-to-out, comparator regeneration, routing and setup) and
// held until after e2 (the quantizer keeps its decision latched until the next
// strobe). For STA, TH is a 2-cycle path from the CMP_STROBE launch flop.
// Each TH bit is registered before the popcount, so an unresolved comparator
// can only change the code by one LSB.
`timescale 1ns / 1ps
`default_nettype none

module eeg_digital_top #(
    parameter int DAC_LOAD_CYCLE = 2          // sets the excess loop delay (2..31)
) (
    input  logic        MCLK,                 // 32.768 MHz
    input  logic        RESET_N,              // asynchronous assert, synchronous deassert
    // SPI slave (mode 0)
    input  logic        SCLK,
    input  logic        CS_N,
    input  logic        MOSI,
    output logic        MISO,
    output logic        MISO_OE,              // MISO pad output enable
    output logic        DRDY_N,               // low while the sample FIFO is not empty
    // raw code debug stream
    output logic        RAW_DATA,
    output logic        RAW_CLK,
    // analog interface
    input  logic [30:0] TH,                   // quantizer thermometer outputs
    output logic [30:0] SEL1,                 // DAC1 element selection, 1 = positive reference
    output logic [30:0] SEL2,                 // DAC2 element selection, 1 = positive reference
    output logic        CMP_STROBE,           // comparator clock (one MCLK cycle per frame)
    output logic        CHOP,                 // chopper clock, 128 kHz (CHOP_FAST = 1) or 64 kHz
    output logic        CHOP_OUT,             // CHOP delayed by CHOP_DLY MCLK cycles
    output logic        CHOP_BLANK,           // output-chopper blanking: 1 MCLK before to BLANK_LEN MCLK after each CHOP_OUT edge
    output logic        AFE_RST,              // CONTROL.AFE_RST
    output logic        CHOP_EN,              // CONTROL.CHOP_EN
    output logic [7:0]  TEST_CFG,             // TEST register (analog test muxes)
    output logic [3:0]  CPF_TRIM,             // ANA_TRIM[3:0]: impedance-boost capacitor trim
    output logic [1:0]  AFE_IBIAS,            // ANA_TRIM[5:4]: AFE bias-current select
    output logic [1:0]  BTRIM_P,              // BOOST_TRIM[1:0]: PMOS-cascode booster units
    output logic [1:0]  BTRIM_N,              // BOOST_TRIM[3:2]: NMOS-cascode booster units
    output logic [9:0]  OFM,                  // electrode-offset DAC magnitude (OFF_CTRL[1:0], OFF_CODE_L)
    output logic        OFS,                  // offset-DAC sign (OFF_CTRL[3])
    output logic [3:0]  OFEN                  // offset-DAC range groups, thermometer of OFF_RANGE
);

    // ------------------------------------------------------------------
    // Reset synchronizer: asynchronous assert, 2-FF synchronous deassert
    // ------------------------------------------------------------------
    logic [1:0] rst_sync;
    logic       rst_n;

    always_ff @(posedge MCLK or negedge RESET_N) begin
        if (!RESET_N) begin
            rst_sync <= 2'b00;
        end else begin
            rst_sync <= {rst_sync[0], 1'b1};
        end
    end

    assign rst_n = rst_sync[1];

    // ------------------------------------------------------------------
    // Frame timing
    // ------------------------------------------------------------------
    logic [4:0] cycle;
    logic       th_capture;
    logic       dac_load;
    logic       cic_en;
    logic       raw_clk;
    logic       chop_fast;
    logic [7:0] chop_dly;
    logic [3:0] blank_len;

    eeg_clkgen #(
        .DAC_LOAD_CYCLE (DAC_LOAD_CYCLE)
    ) u_clkgen (
        .clk        (MCLK),
        .rst_n      (rst_n),
        .chop_fast  (chop_fast),
        .chop_dly   (chop_dly),
        .blank_len  (blank_len),
        .cycle      (cycle),
        .cmp_strobe (CMP_STROBE),
        .th_capture (th_capture),
        .dac_load   (dac_load),
        .cic_en     (cic_en),
        .chop       (CHOP),
        .chop_out   (CHOP_OUT),
        .chop_blank (CHOP_BLANK),
        .raw_clk    (raw_clk)
    );

    // ------------------------------------------------------------------
    // Quantizer capture and code
    // ------------------------------------------------------------------
    logic [30:0] th_q;
    logic [4:0]  code;
    logic [4:0]  k;

    always_ff @(posedge MCLK or negedge rst_n) begin
        if (!rst_n) begin
            th_q <= 31'h0000_7FFF;            // code 15, consistent with the DWA reset (k = 16)
        end else if (th_capture) begin
            th_q <= TH;
        end
    end

    eeg_therm2bin u_therm2bin (
        .th   (th_q),
        .code (code)
    );

    assign k = 5'd31 - code;                  // elements to the positive reference

    // ------------------------------------------------------------------
    // DAC element selection (independent pointers for DAC1 and DAC2)
    // ------------------------------------------------------------------
    logic dwa_en;

    eeg_dwa #(.N(31)) u_dwa1 (
        .clk    (MCLK),
        .rst_n  (rst_n),
        .load   (dac_load),
        .dwa_en (dwa_en),
        .k      (k),
        .sel    (SEL1),
        .ptr    ()
    );

    eeg_dwa #(.N(31)) u_dwa2 (
        .clk    (MCLK),
        .rst_n  (rst_n),
        .load   (dac_load),
        .dwa_en (dwa_en),
        .k      (k),
        .sel    (SEL2),
        .ptr    ()
    );

    // ------------------------------------------------------------------
    // Decimation filter
    // ------------------------------------------------------------------
    logic        filter_clear;
    logic [23:0] cic_data;
    logic        cic_stb;
    logic        cic_valid;
    logic        settling;

    eeg_cic3 u_cic (
        .clk        (MCLK),
        .rst_n      (rst_n),
        .clear      (filter_clear),
        .en         (cic_en),
        .code       (code),
        .dout       (cic_data),
        .dout_stb   (cic_stb),
        .dout_valid (cic_valid),
        .settling   (settling)
    );

    // ------------------------------------------------------------------
    // Sample FIFO
    // ------------------------------------------------------------------
    logic        run;
    logic        ovr_flag;
    logic        ovr_set;
    logic        smp_pop;
    logic [47:0] smp_word;
    logic        fifo_nonempty;
    logic [3:0]  fifo_level;

    eeg_fifo #(.DEPTH(8)) u_fifo (
        .clk       (MCLK),
        .rst_n     (rst_n),
        .clear_seq (filter_clear),
        .smp_stb   (cic_stb & cic_valid),
        .smp_data  (cic_data),
        .run       (run),
        .ovr_flag  (ovr_flag),
        .settling  (settling),
        .ovr_set   (ovr_set),
        .pop       (smp_pop),
        .rd_word   (smp_word),
        .nonempty  (fifo_nonempty),
        .level     (fifo_level)
    );

    assign DRDY_N = ~fifo_nonempty;

    // ------------------------------------------------------------------
    // SPI slave and registers
    // ------------------------------------------------------------------
    logic [7:0] reg_addr;
    logic [7:0] reg_rdata;
    logic       reg_we;
    logic [7:0] reg_wdata;
    logic       cmd_err;
    logic       cmd_err_flag;
    logic       raw_en;

    eeg_spi_slave u_spi (
        .clk       (MCLK),
        .rst_n     (rst_n),
        .sclk      (SCLK),
        .cs_n      (CS_N),
        .mosi      (MOSI),
        .miso      (MISO),
        .miso_oe   (MISO_OE),
        .reg_addr  (reg_addr),
        .reg_rdata (reg_rdata),
        .reg_we    (reg_we),
        .reg_wdata (reg_wdata),
        .smp_word  (smp_word),
        .smp_pop   (smp_pop),
        .cmd_err   (cmd_err)
    );

    // offset-DAC range groups: range 0 = off, 1..4 enable 1..4 groups, 5..7 = 4
    logic [2:0] off_range;
    assign OFEN = {off_range >= 3'd4, off_range >= 3'd3, off_range >= 3'd2, off_range >= 3'd1};

    eeg_regs u_regs (
        .clk           (MCLK),
        .rst_n         (rst_n),
        .addr          (reg_addr),
        .rdata         (reg_rdata),
        .we            (reg_we),
        .wdata         (reg_wdata),
        .fifo_nonempty (fifo_nonempty),
        .settling      (settling),
        .fifo_level    (fifo_level),
        .ovr_set       (ovr_set),
        .cmd_err_set   (cmd_err),
        .run           (run),
        .filter_clear  (filter_clear),
        .dwa_en        (dwa_en),
        .raw_en        (raw_en),
        .afe_rst       (AFE_RST),
        .chop_en       (CHOP_EN),
        .chop_fast     (chop_fast),
        .chop_dly      (chop_dly),
        .test_cfg      (TEST_CFG),
        .cpf_trim      (CPF_TRIM),
        .afe_ibias     (AFE_IBIAS),
        .blank_len     (blank_len),
        .btrim_p       (BTRIM_P),
        .btrim_n       (BTRIM_N),
        .off_mag       (OFM),
        .off_sign      (OFS),
        .off_range     (off_range),
        .ovr_flag      (ovr_flag),
        .cmd_err_flag  (cmd_err_flag)
    );

    // ------------------------------------------------------------------
    // Raw code serializer (debug)
    // ------------------------------------------------------------------
    eeg_raw u_raw (
        .clk        (MCLK),
        .rst_n      (rst_n),
        .raw_en     (raw_en),
        .cycle      (cycle),
        .raw_clk    (raw_clk),
        .code       (code),
        .raw_data_o (RAW_DATA),
        .raw_clk_o  (RAW_CLK)
    );

endmodule

`default_nettype wire
