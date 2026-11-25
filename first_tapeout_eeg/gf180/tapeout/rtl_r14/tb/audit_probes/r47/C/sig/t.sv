module t; logic c = 0; always #5 c = ~c; integer n = 0; always @(posedge c) n = n + 1;
initial begin #2000000000; $display("PASS: t (closing line)"); $finish; end endmodule
