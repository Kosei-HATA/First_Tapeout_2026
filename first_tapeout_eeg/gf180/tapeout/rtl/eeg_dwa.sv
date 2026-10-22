// eeg_dwa - data weighted averaging element selection for one N-element unit DAC.
//
// Input k = number of elements to connect to the positive reference (the ADC
// uses k = 31 - c). The other N - k elements go to the negative reference.
//
// dwa_en = 1: sel has exactly k ones at consecutive positions p, p+1, ...,
//             p+k-1 (mod N), where p is the pointer. At each load the
//             pointer advances: p <- (p + k) mod N.
// dwa_en = 0: thermometer selection (elements 0..k-1); the pointer is held.
//
// sel and the pointer change only at load (the dac_load strobe), so the DAC
// switch drivers see one transition per modulator frame.
//
// Reset state: pointer 0 and sel = elements 0..(N+1)/2-1 (k = 16 for N = 31,
// i.e. code 15). This matches the reset state of the XSPICE controller model
// (adc_ctrl_event: "initial/reset code=15 (k=16), pointer=0").
`timescale 1ns / 1ps
`default_nettype none

module eeg_dwa #(
    parameter int N  = 31,                  // number of unit elements
    parameter int KW = $clog2(N + 1),       // width of k (5 for N = 31)
    parameter int PW = $clog2(N)            // width of the pointer (5 for N = 31)
) (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          load,             // dac_load strobe
    input  logic          dwa_en,
    input  logic [KW-1:0] k,                // 0..N elements to the positive reference
    output logic [N-1:0]  sel,              // 1 = element connected to the positive reference
    output logic [PW-1:0] ptr               // DWA pointer (first element of the next run)
);

    localparam int             RESET_K   = (N + 1) / 2;
    localparam logic [N-1:0]   RESET_SEL = {{(N - RESET_K){1'b0}}, {RESET_K{1'b1}}};
    localparam logic [PW:0]    N_P       = N;

    logic [N-1:0]   therm;      // k ones at positions 0..k-1
    logic [2*N-1:0] dbl;        // {therm, therm} shifted left by the pointer
    logic [N-1:0]   sel_rot;    // therm rotated left by ptr (mod N)
    logic [PW:0]    ptr_sum;    // ptr + k, 0 .. 2N-1
    logic [PW:0]    ptr_sub;    // ptr + k - N
    logic [PW-1:0]  ptr_nxt;    // (ptr + k) mod N

    genvar j;
    for (j = 0; j < N; j = j + 1) begin : g_therm
        assign therm[j] = (k > j);
    end

    // Rotation by ptr within N bits: the upper half of the doubled vector
    // shifted left by ptr holds therm[(j - ptr) mod N] at position j.
    assign dbl     = {therm, therm} << ptr;
    assign sel_rot = dbl[2*N-1:N];

    // ptr <= N-1 and k <= N, so one conditional subtraction is enough.
    assign ptr_sum = ptr + k;
    assign ptr_sub = ptr_sum - N_P;
    assign ptr_nxt = (ptr_sum >= N_P) ? ptr_sub[PW-1:0] : ptr_sum[PW-1:0];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sel <= RESET_SEL;
            ptr <= '0;
        end else if (load) begin
            if (dwa_en) begin
                sel <= sel_rot;
                ptr <= ptr_nxt;
            end else begin
                sel <= therm;
            end
        end
    end

endmodule

`default_nettype wire
