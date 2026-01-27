# 1. Read standard cell library
read_liberty sky130_fd_sc_hd__tt_025C_1v80.lib

# 2. Read synthesized netlist
read_verilog netlist.v

# 3. Set top module
link_design riscv_core

#4. Read SDC
read_sdc constraints.sdc

# 5. SETUP timing report ONLY
report_checks -path_delay max -group_count 1 > timing_report.rpt

# 6. Exit
exit
