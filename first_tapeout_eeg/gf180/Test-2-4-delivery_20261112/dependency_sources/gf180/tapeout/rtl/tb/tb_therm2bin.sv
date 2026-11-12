// tb_therm2bin - popcount conversion: all clean thermometer codes, every
// single-bit bubble on every code, and random patterns.
`timescale 1ns / 1ps

module tb_therm2bin;

    logic [30:0] th;
    logic [4:0]  code;

    eeg_therm2bin dut (
        .th   (th),
        .code (code)
    );

    integer errors = 0;
    integer checks = 0;
    integer seed   = 11;

    function automatic integer popc(input logic [30:0] v);
        integer n;
        n = 0;
        for (int i = 0; i < 31; i++) n = n + v[i];
        return n;
    endfunction

    function automatic logic [30:0] therm(input integer n);
        logic [30:0] v;
        v = '0;
        for (int i = 0; i < n; i++) v[i] = 1'b1;
        return v;
    endfunction

    task automatic check(input logic [30:0] v);
        th = v;
        #1;
        checks = checks + 1;
        if (code !== popc(v)) begin
            errors = errors + 1;
            if (errors < 10) $display("ERROR th=%08h code=%0d expected %0d", v, code, popc(v));
        end
    endtask

    initial begin
        // clean thermometer codes 0..31
        for (int n = 0; n <= 31; n++) check(therm(n));
        // every single-bit bubble on every clean code
        for (int n = 0; n <= 31; n++)
            for (int b = 0; b < 31; b++)
                check(therm(n) ^ (31'd1 << b));
        // random patterns
        for (int i = 0; i < 100000; i++) check($random(seed));

        if (errors == 0) $display("PASS: tb_therm2bin (%0d patterns)", checks);
        else             $display("FAIL: tb_therm2bin (%0d errors in %0d patterns)", errors, checks);
        $finish;
    end

endmodule
