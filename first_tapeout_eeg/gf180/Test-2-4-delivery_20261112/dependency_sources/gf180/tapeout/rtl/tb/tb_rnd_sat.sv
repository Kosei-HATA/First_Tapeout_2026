// tb_rnd_sat - eeg_rnd_sat (37 -> 24 bits, >> 12, ties to even, saturation)
// against vectors from the Python golden model (model/gen_vectors.py).
// Vector file lines: "<din 37-bit hex> <dout 24-bit hex>"; +vec=<file>.
`timescale 1ns / 1ps

module tb_rnd_sat;

    logic [36:0] din;
    logic [23:0] dout;

    eeg_rnd_sat #(.WI(37), .SH(12), .WO(24)) dut (
        .din  (din),
        .dout (dout)
    );

    string       vec_file;
    integer      fd;
    integer      n;
    integer      count = 0;
    integer      errors = 0;
    logic [39:0] v_in;
    logic [23:0] v_out;

    initial begin
        if (!$value$plusargs("vec=%s", vec_file)) vec_file = "build/rnd_sat.vec";
        fd = $fopen(vec_file, "r");
        if (fd == 0) begin
            $display("FAIL: tb_rnd_sat (cannot open %s)", vec_file);
            $finish;
        end
        while (!$feof(fd)) begin
            n = $fscanf(fd, "%h %h\n", v_in, v_out);
            if (n != 2) break;
            din = v_in[36:0];
            #1;
            count = count + 1;
            if (dout !== v_out) begin
                errors = errors + 1;
                if (errors <= 10) $display("ERROR din=%010h dout=%06h expected %06h", din, dout, v_out);
            end
        end
        $fclose(fd);
        if (errors == 0 && count > 0) $display("PASS: tb_rnd_sat (%0d vectors)", count);
        else                          $display("FAIL: tb_rnd_sat (%0d errors in %0d vectors)", errors, count);
        $finish;
    end

endmodule
