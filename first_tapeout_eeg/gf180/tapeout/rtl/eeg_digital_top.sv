// eeg_digital_top - digital block of the GF180 EEG ADC (single channel).
//
// Single clock domain: MCLK = 32.768 MHz from an external oscillator.
// One modulator frame = 32 MCLK cycles (fs = 1.024 MHz). See README.md for the
// frame timing diagram, register map and SPI frame format.
//
// The quantizer capture, the thermometer-to-binary converter and the two DWA
// selectors are in the separate ADC-side block eeg_adc_dig (placed in the ADC,
// gate 1, 10/23); this block sends it the frame strobes and receives the code.
// eeg_digital_sys.sv connects the two as on the chip.
//
// Data path per frame (e_n = rising MCLK edge that starts frame cycle n):
//   e0  CMP_STROBE rises; the quantizer compares and latches its decision.
//   e2  eeg_adc_dig captures TH[30:0] (TH_CAPTURE = cycle 1);
//       CODE = popcount(TH), k = 31 - CODE
//   e3  eeg_adc_dig updates SEL1/SEL2 from k (DAC_LOAD = cycle DAC_LOAD_CYCLE = 2).
//       Excess loop delay CMP_STROBE -> SEL = (DAC_LOAD_CYCLE + 1) MCLK = 91.6 ns.
//   e4  CIC integrators take x = 2*CODE - 31 (cic_en = cycle 3).
//
// TEST_CFG[5] (ADC_ZERO) holds CHOP_BLANK high (the AFE output chopper stays
// open while the analog side shorts the ADC input); TEST_CFG[7:6] (DBG_SEL)
// put timing signals on the RAW pads while the raw stream is off (eeg_raw.sv).
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
    // ADC-side digital block (eeg_adc_dig): TH capture, code, DWA
    output logic        ADC_RST_N,            // synchronized reset for eeg_adc_dig
    output logic        TH_CAPTURE,           // frame cycle 1: eeg_adc_dig captures TH at its end (e2)
    output logic        DAC_LOAD,             // frame cycle DAC_LOAD_CYCLE: SEL1/SEL2 update at its end
    output logic        DWA_EN,               // CONTROL.DWA_EN
    input  logic [4:0]  CODE,                 // quantizer code from eeg_adc_dig (popcount of the captured TH)
    // analog interface
    output logic        CMP_STROBE,           // comparator clock (one MCLK cycle per frame)
    output logic        DAC_CLK,              // DAC1 update: high one MCLK, from one MCLK after SEL1/SEL2 change
    output logic        CHOP,                 // chopper clock, 128 kHz (CHOP_FAST = 1) or 64 kHz
    output logic        CHOP_OUT,             // CHOP delayed by CHOP_DLY MCLK cycles
    output logic        CHOP_BLANK,           // output-chopper blanking: 1 MCLK before to BLANK_LEN MCLK after each CHOP_OUT edge; held high by TEST_CFG[5]
    output logic        AFE_RST,              // CONTROL.AFE_RST
    output logic        CHOP_EN,              // CONTROL.CHOP_EN
    output logic [7:0]  TEST_CFG,             // TEST register: [4:0] analog test mux, [5] ADC_ZERO, [7:6] DBG_SEL
    output logic [3:0]  CPF_TRIM,             // ANA_TRIM[3:0]: impedance-boost capacitor trim
    output logic [1:0]  AFE_IBIAS,            // ANA_TRIM[5:4]: AFE bias-current select
    output logic [1:0]  BTRIM_P,              // BOOST_TRIM[1:0]: PMOS-cascode booster units
    output logic [1:0]  BTRIM_N,              // BOOST_TRIM[3:2]: NMOS-cascode booster units
    output logic [9:0]  OFM,                  // electrode-offset DAC magnitude (OFF_CTRL[1:0], OFF_CODE_L)
    output logic        OFS,                  // offset-DAC sign (OFF_CTRL[3])
    output logic [3:0]  OFEN,                 // offset-DAC range groups, thermometer of OFF_RANGE
    output logic        CHOP1                 // OTA1 chopper, 1 = phase A (CHOP1 register, eeg_chop1.sv)
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
    logic       chop_blank;

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
        .chop_blank (chop_blank),
        .raw_clk    (raw_clk)
    );

    // ------------------------------------------------------------------
    // ADC-side digital block (eeg_adc_dig): strobes out, code in
    // ------------------------------------------------------------------
    logic [4:0] code;
    logic       dwa_en;

    assign ADC_RST_N  = rst_n;
    assign TH_CAPTURE = th_capture;
    assign DAC_LOAD   = dac_load;
    assign DWA_EN     = dwa_en;
    assign code       = CODE;

    // ADC_ZERO (TEST_CFG[5]) keeps the output chopper blanked. Both inputs are
    // registers; TEST_CFG only changes on a register write.
    assign CHOP_BLANK = chop_blank | TEST_CFG[5];

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
    logic [2:0] chop1_rate;
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
        .chop1_rate    (chop1_rate),
        .ovr_flag      (ovr_flag),
        .cmd_err_flag  (cmd_err_flag)
    );

    // ------------------------------------------------------------------
    // DAC1 update clock: SEL1 changes at e(DAC_LOAD_CYCLE + 1); DAC_CLK rises one
    // MCLK later and stays high for one MCLK. The DAC1 array (common-break drive,
    // gf180/tapeout/adc/eeg_dac1.spice) opens all its switches at the DAC_CLK
    // rising edge, latches SEL1 during a ~2 ns pulse and then closes the selected
    // switches, so SEL1 only has to settle within one MCLK.
    // ------------------------------------------------------------------
    localparam logic [4:0] DAC_CLK_CYCLE = DAC_LOAD_CYCLE + 1;   // high in cycle DAC_LOAD_CYCLE + 2

    always_ff @(posedge MCLK or negedge rst_n) begin
        if (!rst_n) begin
            DAC_CLK <= 1'b0;
        end else begin
            DAC_CLK <= (cycle == DAC_CLK_CYCLE);
        end
    end

    // ------------------------------------------------------------------
    // OTA1 chopper (a few kHz, edges at e16)
    // ------------------------------------------------------------------
    eeg_chop1 u_chop1 (
        .clk        (MCLK),
        .rst_n      (rst_n),
        .cycle      (cycle),
        .chop1_rate (chop1_rate),
        .chop1      (CHOP1)
    );

    // ------------------------------------------------------------------
    // Raw code serializer and timing debug outputs (RAW pads)
    // ------------------------------------------------------------------
    eeg_raw u_raw (
        .clk        (MCLK),
        .rst_n      (rst_n),
        .raw_en     (raw_en),
        .cycle      (cycle),
        .raw_clk    (raw_clk),
        .code       (code),
        .dbg_sel    (TEST_CFG[7:6]),
        .dbg_clk    ({CHOP_BLANK, CHOP, CMP_STROBE}),
        .dbg_data   ({CHOP1, CHOP_OUT, DAC_CLK}),
        .raw_data_o (RAW_DATA),
        .raw_clk_o  (RAW_CLK)
    );

endmodule

`default_nettype wire
