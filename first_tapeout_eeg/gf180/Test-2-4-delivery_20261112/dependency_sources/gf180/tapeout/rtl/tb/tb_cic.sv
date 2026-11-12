// tb_cic - eeg_cic3 bit-exact against the Python golden model.
//
// +ops=<file>  operation stream (one byte per operation, see model/cic_golden.py)
//              0x00..0x1F input code, 0x80 clear, 0xC0|code clear + input in
//              the same cycle (the input is discarded)
// +gold=<file> one line per output strobe: "<data 24-bit hex> <valid>"
// +gaps        insert random idle cycles between inputs (1 in 16)
//
// Every output strobe is compared (data, valid flag and the settling output),
// including the invalid start-up strobes, and the number of strobes must equal
// the number of golden lines. Inputs are applied back to back (en in
// consecutive cycles, much faster than in the chip) so long streams run in
// reasonable time; the comb pipeline is independent of the input spacing.
// Before a clear the filter is left idle for 6 cycles so that no output is in
// flight (in the chip a clear in the 5 cycles after a decimation event
// discards that output, which the golden model does not model).
`timescale 1ns / 1ps

module tb_cic;

    logic        clk = 1'b0;
    logic        rst_n = 1'b0;
    logic        clear = 1'b0;
    logic        en = 1'b0;
    logic [4:0]  code = 5'd0;
    logic [23:0] dout;
    logic        dout_stb;
    logic        dout_valid;
    logic        settling;

    eeg_cic3 dut (
        .clk        (clk),
        .rst_n      (rst_n),
        .clear      (clear),
        .en         (en),
        .code       (code),
        .dout       (dout),
        .dout_stb   (dout_stb),
        .dout_valid (dout_valid),
        .settling   (settling)
    );

    always #5 clk = ~clk;

    string  ops_file;
    string  gold_file;
    string  name;
    integer fo;
    integer fg;
    integer op;
    integer seed = 3;
    bit     gaps = 1'b0;
    integer nops = 0;
    integer nstrobes = 0;
    integer nvalid = 0;
    integer errors = 0;
    integer r;
    logic [23:0] g_data;
    integer      g_valid;

    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 10) $display("ERROR @%0t strobe %0d: %s", $time, nstrobes, msg);
    endtask

    // compare every output strobe with the next golden line
    always @(posedge clk) begin
        if (rst_n && dout_stb) begin
            r = $fscanf(fg, "%h %d\n", g_data, g_valid);
            if (r != 2) begin
                err("more output strobes than golden lines");
            end else begin
                if (dout !== g_data || dout_valid !== g_valid[0])
                    err($sformatf("dout=%06h valid=%0d expected %06h valid=%0d", dout, dout_valid, g_data, g_valid));
                if (settling !== !g_valid[0])
                    err($sformatf("settling=%0d with valid=%0d", settling, g_valid));
                if (g_valid) nvalid = nvalid + 1;
            end
            nstrobes = nstrobes + 1;
        end
    end

    initial begin
        if (!$value$plusargs("ops=%s", ops_file)) ops_file = "build/cic_stream.ops";
        if (!$value$plusargs("gold=%s", gold_file)) gold_file = "build/cic_stream.gold";
        if (!$value$plusargs("name=%s", name)) name = "cic";
        gaps = $test$plusargs("gaps");
        fo = $fopen(ops_file, "rb");
        fg = $fopen(gold_file, "r");
        if (fo == 0 || fg == 0) begin
            $display("FAIL: tb_cic %s (cannot open %s or %s)", name, ops_file, gold_file);
            $finish;
        end

        repeat (3) @(negedge clk);
        if (settling !== 1'b1) err("settling must be 1 after reset");
        rst_n = 1'b1;
        @(negedge clk);

        op = $fgetc(fo);
        while (op != -1) begin
            nops = nops + 1;
            if (op == 8'h80) begin
                en = 1'b0;
                repeat (6) @(negedge clk);
                clear = 1'b1;
                @(negedge clk);
                clear = 1'b0;
                if (settling !== 1'b1) err("settling must be 1 after clear");
            end else if (op >= 8'hC0) begin
                en = 1'b0;
                repeat (6) @(negedge clk);
                clear = 1'b1;
                en    = 1'b1;
                code  = op[4:0];
                @(negedge clk);
                clear = 1'b0;
                en    = 1'b0;
                if (settling !== 1'b1) err("settling must be 1 after clear");
            end else begin
                if (gaps && (($random(seed) & 15) == 0)) begin
                    en = 1'b0;
                    @(negedge clk);
                end
                en   = 1'b1;
                code = op[4:0];
                @(negedge clk);
            end
            op = $fgetc(fo);
        end
        en = 1'b0;
        repeat (10) @(negedge clk);

        r = $fscanf(fg, "%h %d\n", g_data, g_valid);
        if (r == 2) err("fewer output strobes than golden lines");
        $fclose(fo);
        $fclose(fg);

        if (errors == 0 && nstrobes > 0)
            $display("PASS: tb_cic %s (%0d operations, %0d output strobes bit-exact, %0d valid)",
                     name, nops, nstrobes, nvalid);
        else
            $display("FAIL: tb_cic %s (%0d errors, %0d strobes, %0d operations)", name, errors, nstrobes, nops);
        $finish;
    end

endmodule
