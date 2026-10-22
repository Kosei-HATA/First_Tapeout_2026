// eeg_adc_dig - ADC-side digital block of the GF180 EEG ADC: quantizer capture,
// thermometer-to-binary conversion and the two DWA element selectors.
//
// It sits in the ADC, at the east end of its center band next to the quantizer and
// the DAC switch drivers (gate 1, 10/23: documentation/gf180_gate1_20261023.md), so
// the 31 TH lines and the 62 SEL lines stay inside the ADC and only the 5-bit code
// crosses to eeg_digital_top. It runs on the same MCLK and reset as eeg_digital_top,
// which supplies the frame strobes (eeg_digital_sys.sv shows the connection).
//
// Timing (unchanged by the split; e_n = rising MCLK edge that starts frame cycle n):
//   e2  TH[30:0] is captured into th_q (TH_CAPTURE = cycle 1).
//       CODE = popcount(th_q), k = 31 - CODE
//   e3  SEL1/SEL2 update from k (DAC_LOAD = cycle DAC_LOAD_CYCLE = 2).
// eeg_digital_top uses CODE at e4 (CIC) and at e0 (raw serializer): a single-cycle
// path from th_q through the popcount and the route between the two blocks.
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

module eeg_adc_dig (
    input  logic        MCLK,                 // 32.768 MHz, the clock of eeg_digital_top
    input  logic        RST_N,                // synchronized reset from eeg_digital_top (ADC_RST_N)
    input  logic        TH_CAPTURE,           // frame cycle 1: TH is captured at its end (e2)
    input  logic        DAC_LOAD,             // frame cycle DAC_LOAD_CYCLE: SEL1/SEL2 update at its end
    input  logic        DWA_EN,               // CONTROL.DWA_EN
    input  logic [30:0] TH,                   // quantizer thermometer outputs
    output logic [4:0]  CODE,                 // quantizer code c = popcount(TH) to eeg_digital_top
    output logic [30:0] SEL1,                 // DAC1 element selection, 1 = positive reference
    output logic [30:0] SEL2                  // DAC2 element selection, 1 = positive reference
);

    // ------------------------------------------------------------------
    // Quantizer capture and code
    // ------------------------------------------------------------------
    logic [30:0] th_q;
    logic [4:0]  k;

    always_ff @(posedge MCLK or negedge RST_N) begin
        if (!RST_N) begin
            th_q <= 31'h0000_7FFF;            // code 15, consistent with the DWA reset (k = 16)
        end else if (TH_CAPTURE) begin
            th_q <= TH;
        end
    end

    eeg_therm2bin u_therm2bin (
        .th   (th_q),
        .code (CODE)
    );

    assign k = 5'd31 - CODE;                  // elements to the positive reference

    // ------------------------------------------------------------------
    // DAC element selection (independent pointers for DAC1 and DAC2)
    // ------------------------------------------------------------------
    eeg_dwa #(.N(31)) u_dwa1 (
        .clk    (MCLK),
        .rst_n  (RST_N),
        .load   (DAC_LOAD),
        .dwa_en (DWA_EN),
        .k      (k),
        .sel    (SEL1),
        .ptr    ()
    );

    eeg_dwa #(.N(31)) u_dwa2 (
        .clk    (MCLK),
        .rst_n  (RST_N),
        .load   (DAC_LOAD),
        .dwa_en (DWA_EN),
        .k      (k),
        .sel    (SEL2),
        .ptr    ()
    );

endmodule

`default_nettype wire
