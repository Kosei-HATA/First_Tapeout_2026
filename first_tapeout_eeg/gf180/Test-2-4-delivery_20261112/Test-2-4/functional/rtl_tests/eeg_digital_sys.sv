// eeg_digital_sys - the two digital blocks of the GF180 EEG ADC connected as on
// the chip: eeg_digital_top (clocking, CIC, FIFO, SPI, registers, raw stream) and
// eeg_adc_dig (TH capture, code, DWA; placed in the ADC, gate 1 10/23).
//
// The ports are those of eeg_digital_top before the split (TH in, SEL1/SEL2 out),
// so the integrated testbenches see the same interface. On the chip the blocks are
// placed and routed separately; this file is the reference for the wires between
// them: MCLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN and CODE[4:0].
`timescale 1ns / 1ps
`default_nettype none

module eeg_digital_sys #(
    parameter int DAC_LOAD_CYCLE = 2          // sets the excess loop delay (2..31)
) (
    input  logic        MCLK,
    input  logic        RESET_N,
    input  logic        SCLK,
    input  logic        CS_N,
    input  logic        MOSI,
    output logic        MISO,
    output logic        MISO_OE,
    output logic        DRDY_N,
    output logic        RAW_DATA,
    output logic        RAW_CLK,
    input  logic [30:0] TH,
    output logic [30:0] SEL1,
    output logic [30:0] SEL2,
    output logic        CMP_STROBE,
    output logic        DAC_CLK,
    output logic        CHOP,
    output logic        CHOP_OUT,
    output logic        CHOP_BLANK,
    output logic        AFE_RST,
    output logic        CHOP_EN,
    output logic [7:0]  TEST_CFG,
    output logic [3:0]  CPF_TRIM,
    output logic [1:0]  AFE_IBIAS,
    output logic [1:0]  BTRIM_P,
    output logic [1:0]  BTRIM_N,
    output logic [9:0]  OFM,
    output logic        OFS,
    output logic [3:0]  OFEN,
    output logic        CHOP1
);

    logic       adc_rst_n;
    logic       th_capture;
    logic       dac_load;
    logic       dwa_en;
    logic [4:0] code;

    eeg_digital_top #(
        .DAC_LOAD_CYCLE (DAC_LOAD_CYCLE)
    ) u_top (
        .MCLK       (MCLK),
        .RESET_N    (RESET_N),
        .SCLK       (SCLK),
        .CS_N       (CS_N),
        .MOSI       (MOSI),
        .MISO       (MISO),
        .MISO_OE    (MISO_OE),
        .DRDY_N     (DRDY_N),
        .RAW_DATA   (RAW_DATA),
        .RAW_CLK    (RAW_CLK),
        .ADC_RST_N  (adc_rst_n),
        .TH_CAPTURE (th_capture),
        .DAC_LOAD   (dac_load),
        .DWA_EN     (dwa_en),
        .CODE       (code),
        .CMP_STROBE (CMP_STROBE),
        .DAC_CLK    (DAC_CLK),
        .CHOP       (CHOP),
        .CHOP_OUT   (CHOP_OUT),
        .CHOP_BLANK (CHOP_BLANK),
        .AFE_RST    (AFE_RST),
        .CHOP_EN    (CHOP_EN),
        .TEST_CFG   (TEST_CFG),
        .CPF_TRIM   (CPF_TRIM),
        .AFE_IBIAS  (AFE_IBIAS),
        .BTRIM_P    (BTRIM_P),
        .BTRIM_N    (BTRIM_N),
        .OFM        (OFM),
        .OFS        (OFS),
        .OFEN       (OFEN),
        .CHOP1      (CHOP1)
    );

    eeg_adc_dig u_adc (
        .MCLK       (MCLK),
        .RST_N      (adc_rst_n),
        .TH_CAPTURE (th_capture),
        .DAC_LOAD   (dac_load),
        .DWA_EN     (dwa_en),
        .TH         (TH),
        .CODE       (code),
        .SEL1       (SEL1),
        .SEL2       (SEL2)
    );

endmodule

`default_nettype wire
