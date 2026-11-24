// power_vcd_r14 - switching activity of the r14 macro's gate-level netlist for OpenSTA's report_power
// (run_power_r14.sh): a third root next to gl_sdf_r14 and gl_shadow_r14 (gf180/tapeout/digital/gl_r14, zero delay).
// It waits for the sequencer's RUN (gl_sdf_r14's part 3: START, then the host reads every sample over SPI),
// lets 0.2 ms pass and writes the VCD of gl_shadow_r14.g (the netlist) for 1 ms (32,768 MCLK cycles), then ends
// the simulation. The r13 macro's activity (10/29, vcd_dump.sv) is of tb_e2e in the same state: RUN, the CIC
// running, the host reading the samples.
`timescale 1ns / 1ps
module power_vcd_r14;
    initial begin
        wait (gl_sdf_r14.dut.u_seq.state == 4'd6);     // ST_RUN (rtl/spec/eeg_regs_defs.svh)
        $display("power_vcd_r14: RUN at %0t ps", $time);
        #200000;
        $dumpfile(`VCD);
        $dumpvars(0, gl_shadow_r14.g);
        #1000000;
        $dumpflush;
        $display("power_vcd_r14: 1 ms written, up to %0t ps", $time);
        $finish;
    end
endmodule
