import cocotb
from cocotb.triggers import Timer, RisingEdge
from cocotb.clock import Clock

async def setup_dut(dut):
    """Initialize signals and start clock"""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    
    # Set initial signal values
    dut.rst_n.value = 1
    dut.start.value = 0
    dut.opcode.value = 0
    dut.A.value = 0
    dut.B.value = 0
    # NEW: Drive diss_clk to 0 to ensure the ALU clock is enabled
    dut.diss_clk.value = 0 
    
    # Perform a Power-on reset
    dut.rst_n.value = 0
    await Timer(20, units="ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_reset_during_busy(dut):
    """Test that rst_n forces busy to 0 even during a DIV operation"""
    await setup_dut(dut)

    # 1. Start a multi-cycle Division operation
    dut.A.value = 100
    dut.B.value = 5
    dut.opcode.value = 0x9 
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    
    # 2. Verify ALU has moved out of IDLE and is now busy
    # CHANGE: Access busy via the 'u_alu' instance inside 'top'
    await RisingEdge(dut.clk)
    assert dut.u_alu.busy.value == 1, "ALU should be BUSY during Division"

    # 3. THE ECO TEST: Assert Reset mid-operation
    dut._log.info("Asserting reset while ALU is busy...")
    dut.rst_n.value = 0
    
    await Timer(1, units="ns")

    # 4. Final Verification
    # CHANGE: Access busy via 'u_alu'
    assert dut.u_alu.busy.value == 0, "ERROR: busy signal failed to reset to 0!"
    dut._log.info("SUCCESS: busy signal correctly reset to 0.")

def test_alu_runner():
    import os
    from pathlib import Path
    from cocotb_tools.runner import get_runner

    sim = os.getenv("SIM", "icarus")
    # Correct the project path to reach the 'sources' folder outside 'tests'
    proj_path = Path(__file__).resolve().parent.parent 

    sources = [
        proj_path / "sources" / "gate_netlist.v",
        proj_path / "sources" / "my_cells.v"
    ]

    runner = get_runner(sim)
    runner.build(sources=sources, hdl_toplevel="top", always=True)
    runner.test(hdl_toplevel="top", test_module="test_hidden")