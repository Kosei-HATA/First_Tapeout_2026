// Testbench: feed a recorded 1-bit stream, dump decimated outputs.
`timescale 1us/1ns
module cic_tb;
    reg clk = 0, rst_n = 0, bit_in = 0;
    wire [23:0] data_out;
    wire data_valid;
    integer fd, ofd, code;
    reg [31:0] bitfile_data;

    cic_decimator dut(.clk(clk), .rst_n(rst_n), .bit_in(bit_in),
                      .data_out(data_out), .data_valid(data_valid));

    always #31.25 clk = ~clk;   // 16 kHz

    initial begin
        fd  = $fopen("bitstream_in.txt", "r");
        ofd = $fopen("cic_out.txt", "w");
        repeat (4) @(posedge clk);
        rst_n = 1;
        while (!$feof(fd)) begin
            @(negedge clk);
            code = $fscanf(fd, "%d\n", bitfile_data);
            if (code == 1) bit_in = bitfile_data[0];
            if (data_valid) $fdisplay(ofd, "%d", $signed(data_out));
        end
        $fclose(fd); $fclose(ofd);
        $finish;
    end
endmodule
