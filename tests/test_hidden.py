import cocotb
from cocotb.triggers import Timer, RisingEdge
from cocotb.clock import Clock

async def setup_dut(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    
    # Set initial signal values
    dut.rst_n.value = 1
    dut.start.value = 0
    dut.opcode.value = 0
    dut.A.value = 0
    dut.B.value = 0
    
    # Perform a Power-on reset to synchronize the FSM
    dut.rst_n.value = 0
    await Timer(20, units="ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_reset_during_busy(dut):
    """Test that rst_n forces busy to 0 even during a DIV operation"""
    await setup_dut(dut)

    # 1. Start a multi-cycle Division operation (8 cycles)
    dut.A.value = 100
    dut.B.value = 5
    dut.opcode.value = 0x9 
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    
    # 2. Verify ALU has moved out of IDLE and is now busy
    await RisingEdge(dut.clk)
    assert dut.busy.value == 1, "ALU should be BUSY during Division"

    # 3. THE ECO TEST: Assert Reset mid-operation
    dut._log.info("Asserting reset while ALU is busy...")
    dut.rst_n.value = 0

    await Timer(1, units="ns")

    # 4. Final Verification
    # Baseline Netlist: Will FAIL (busy remains 1 because rst_n is disconnected)
    # Patched Netlist: Will PASS (busy drops to 0 immediately)
    assert dut.busy.value == 0, "ERROR: busy signal failed to reset to 0! Reset connectivity missing."
    dut._log.info("SUCCESS: busy signal correctly reset to 0.")

def test_alu_runner():
    import os
    from pathlib import Path
    from cocotb_tools.runner import get_runner

    sim = os.getenv("SIM", "icarus")

    test_dir = Path(__file__).resolve().parent 

    sources = [
        test_dir / "sources" / "gate_netlist.v",
        test_dir / "sources" / "my_cells.v"
    ]

    # Debug: This will help you see where it's looking in the logs
    print(f"Checking for file at: {sources[0]}")

    runner = get_runner(sim)
    runner.build(sources=sources, hdl_toplevel="top", always=True)
    runner.test(hdl_toplevel="top", test_module="test_hidden")
