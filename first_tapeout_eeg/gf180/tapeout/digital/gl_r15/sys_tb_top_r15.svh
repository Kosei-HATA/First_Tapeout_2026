// sys_adc_r15.sv's view of tb_top_r14 (11/25): the code tb_top_r14 gives at the coming e2 (its CODE stream: the extreme
// code 31 while ovl_force, else build/top_r14.codes at cidx; tb_top_r14.sv, "CODE stream and logs") and the variables
// that code depends on.
`define SYS_NEXT_CODE (tb_top_r14.ovl_force ? 5'd31 : tb_top_r14.codes[tb_top_r14.cidx % tb_top_r14.ncodes])
`define SYS_NEXT_EVT tb_top_r14.cidx or tb_top_r14.ovl_force or tb_top_r14.ncodes
