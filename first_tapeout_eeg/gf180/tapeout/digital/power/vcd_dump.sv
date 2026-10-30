// vcd_dump - switching activity of the two gate-level macros for OpenSTA's report_power
// (run_power.sh): a third root next to tb_e2e and gl_shadow (tb/gl_shadow.sv), it writes
// the VCD of gl_shadow.g_adc and gl_shadow.g_top from 0.2 ms (past the pre-roll and the
// start command) for 1 ms (1024 frames, 32768 MCLK cycles) and ends the simulation.
`timescale 1ns / 1ps
module vcd_dump;
    initial begin
        #200000;
        $dumpfile(`VCD);
        $dumpvars(0, gl_shadow.g_adc);
        $dumpvars(0, gl_shadow.g_top);
        #1000000;
        $dumpflush;
        $display("vcd_dump: 0.2 .. 1.2 ms written");
        $finish;
    end
endmodule
