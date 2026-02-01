set_units -time ns -resistance kohm -capacitance pF -voltage V -current mA

create_clock -name clk -period 3.2 [get_ports clk]

set_clock_uncertainty 0.1 [get_clocks clk]
set_clock_transition 0.1 [get_clocks clk]