// power_vcd_r15 - switching activity of the r15 macro's gate-level netlist (r15m13; power_vcd_r14.sv for r15, 11/28) for OpenSTA's
// report_power (run_power_r15.sh): a third root next to gl_sdf_r15 and gl_shadow_r15 (gf180/tapeout/digital/gl_r15, zero delay).
// It waits for the sequencer's RUN (gl_sdf_r15's part 3: START, then the host reads every sample over SPI),
// lets 0.2 ms pass and writes the VCD of gl_shadow_r15.g (the netlist) for 1 ms (32,768 MCLK cycles), then ends
// the simulation. The r13 macro's activity (10/29, vcd_dump.sv) is of tb_e2e in the same state: RUN, the CIC
// running, the host reading the samples.
`timescale 1ns / 1ps
module power_vcd_r15;
    initial begin
        wait (gl_sdf_r15.dut.u_seq.state == 4'd6);     // ST_RUN (rtl_r15/spec/eeg_regs_defs.svh)
        $display("power_vcd_r15: RUN at %0t ps", $time);
        #200000;
        $dumpfile(`VCD);
        $dumpvars(0, gl_shadow_r15.g);
        #1000000;
        $dumpflush;
        $display("power_vcd_r15: 1 ms written, up to %0t ps", $time);
        $finish;
    end
endmodule
