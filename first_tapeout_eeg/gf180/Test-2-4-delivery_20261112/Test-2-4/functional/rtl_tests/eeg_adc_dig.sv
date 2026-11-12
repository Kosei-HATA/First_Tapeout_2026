// eeg_adc_dig - ADC-side digital block of the GF180 EEG ADC: quantizer capture,
// thermometer-to-binary conversion and the two DWA element selectors.
//
// It sits in the ADC, at the east end of its center band next to the quantizer and
// the DAC switch drivers (gate 1, 10/23: documentation/gf180_gate1_20261023.md), so
// the 31 TH lines and the 62 SEL lines stay inside the ADC and only the 5-bit code
// crosses to eeg_digital_top. It runs on the same MCLK and reset as eeg_digital_top,
// which supplies the frame strobes (eeg_digital_sys.sv shows the connection).
//
// Timing (unchanged at the ports; e_n = rising MCLK edge that starts frame cycle n):
//   e2  CODE <= popcount(TH), and each DWA samples k = 31 - popcount(TH) and
//       computes its next selection from it (TH_CAPTURE = cycle 1).
//   e3  SEL1/SEL2 update (DAC_LOAD = cycle DAC_LOAD_CYCLE = 2).
// eeg_digital_top uses CODE at e4 (CIC) and at e0 (raw serializer); CODE is a
// register output and changes only at e2.
//
// The popcount, the thermometer and the DWA rotation sit between TH and the
// registers sampled at e2. TH is launched by e0 (see below), so that logic has two
// MCLK periods; the e2 -> e3 step is only a selection (eeg_dwa.sv). In the first
// version (until 10/23) TH went into a 31-bit register th_q at e2 and the whole
// chain ran from th_q to SEL in one period, which failed STA at 3.3 V (ss).
//
// TH timing assumption (no synchronizer on TH): TH is driven by the analog
// quantizer in response to CMP_STROBE, i.e. it is launched by the e0 edge of
// this same clock. It must be settled at e2 (two MCLK periods after the strobe
// edge, minus clock-to-out, comparator regeneration, routing, the popcount and
// rotation logic and setup) and held until after e2 (the quantizer keeps its
// decision latched until the next strobe). For STA, TH is a 2-cycle path
// (eeg_adc_dig.sdc). TH settles within about 4 ns of the strobe, more than 50 ns
// before e2, so a comparator that is still unresolved at e2 (which could make
// the captured code inconsistent by more than one LSB now that the popcount
// precedes the register) would need a regeneration time of over 100 time
// constants.
`timescale 1ns / 1ps
`default_nettype none

module eeg_adc_dig (
    input  logic        MCLK,                 // 32.768 MHz, the clock of eeg_digital_top
    input  logic        RST_N,                // reset from eeg_digital_top (ADC_RST_N), resynchronized here
    input  logic        TH_CAPTURE,           // frame cycle 1: TH is captured at its end (e2)
    input  logic        DAC_LOAD,             // frame cycle DAC_LOAD_CYCLE: SEL1/SEL2 update at its end
    input  logic        DWA_EN,               // CONTROL.DWA_EN
    input  logic [30:0] TH,                   // quantizer thermometer outputs
    output logic [4:0]  CODE,                 // quantizer code c = popcount(TH) at e2, to eeg_digital_top
    output logic [30:0] SEL1,                 // DAC1 element selection, 1 = positive reference
    output logic [30:0] SEL2                  // DAC2 element selection, 1 = positive reference
);

    // ------------------------------------------------------------------
    // Local reset: asynchronous assert, deassert through two flip-flops of this
    // block, so the reset tree here starts at a local flip-flop instead of at
    // the RST_N pin (ADC_RST_N crosses the isolation band from eeg_digital_top).
    // ADC_RST_N deasserts at the edge before frame cycle 0 starts; rst_loc_n follows
    // two edges later, one edge before the first TH_CAPTURE edge (e2 of frame 0).
    // ------------------------------------------------------------------
    logic [1:0] rst_sync;
    logic       rst_loc_n;                    // not rst_n: netgen LVS merges names that differ only in case

    always_ff @(posedge MCLK or negedge RST_N) begin
        if (!RST_N) begin
            rst_sync <= 2'b00;
        end else begin
            rst_sync <= {rst_sync[0], 1'b1};
        end
    end

    assign rst_loc_n = rst_sync[1];

    // ------------------------------------------------------------------
    // Quantizer code
    // ------------------------------------------------------------------
    logic [4:0] code_d;                       // popcount(TH)
    logic [4:0] k_d;                          // elements to the positive reference

    eeg_therm2bin u_therm2bin (
        .th   (TH),
        .code (code_d)
    );

    assign k_d = 5'd31 - code_d;

    always_ff @(posedge MCLK or negedge rst_loc_n) begin
        if (!rst_loc_n) begin
            CODE <= 5'd15;                    // consistent with the DWA reset (k = 16)
        end else if (TH_CAPTURE) begin
            CODE <= code_d;
        end
    end

    // ------------------------------------------------------------------
    // DAC element selection (independent pointers for DAC1 and DAC2)
    // ------------------------------------------------------------------
    eeg_dwa #(.N(31)) u_dwa1 (
        .clk     (MCLK),
        .rst_n   (rst_loc_n),
        .capture (TH_CAPTURE),
        .load    (DAC_LOAD),
        .dwa_en  (DWA_EN),
        .k       (k_d),
        .sel     (SEL1),
        .ptr     ()
    );

    eeg_dwa #(.N(31)) u_dwa2 (
        .clk     (MCLK),
        .rst_n   (rst_loc_n),
        .capture (TH_CAPTURE),
        .load    (DAC_LOAD),
        .dwa_en  (DWA_EN),
        .k       (k_d),
        .sel     (SEL2),
        .ptr     ()
    );

endmodule

`default_nettype wire
