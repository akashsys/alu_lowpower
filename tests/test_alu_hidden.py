import cocotb
from cocotb.triggers import RisingEdge, Timer, ReadOnly
from cocotb.clock import Clock

async def setup_dut(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    # Initial states
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.diss_clk.value = 0
    dut.opcode.value = 0
    dut.A.value = 0
    dut.B.value = 0
    
    await Timer(20, unit="ns")
    dut.rst_n.value = 1
    
    # Wait for the next edge after reset release
    await RisingEdge(dut.clk)
    # Ensure signals have propagated and the state machine is in IDLE
    await Timer(1, unit="ns")

@cocotb.test()
async def test_clamp_value_is_defined(dut):
    await setup_dut(dut)
    # .is_resolvable checks that the value is not X or Z
    assert dut.clamp_obs.value.is_resolvable, "clamp_obs is undefined (X or Z)! Agent must assign it 0 or 1."

@cocotb.test()
async def test_result_matches_clamp_when_disabled(dut):
    await setup_dut(dut)
    
    dut.diss_clk.value = 1
    await Timer(1, unit="ns")
    
    expected_clamp = dut.clamp_obs.value
    assert int(dut.result.value) == int(expected_clamp), f"Result {int(dut.result.value)} does not match clamp_obs {int(expected_clamp)}"


@cocotb.test()
async def test_addition_logic(dut):
    await setup_dut(dut)
    dut.A.value = 10
    dut.B.value = 5
    dut.opcode.value = 0
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    await RisingEdge(dut.clk)
    assert int(dut.result.value) == 15

@cocotb.test()
async def test_multi_cycle_mul(dut):
    await setup_dut(dut)
    
    assert dut.u_alu.busy.value == 0, "ALU was busy before test started!"
    
    dut.A.value = 4
    dut.B.value = 3
    dut.opcode.value = 8   # MUL opcode
    dut.diss_clk.value = 0 # Ensure ALU is enabled
    
    await RisingEdge(dut.clk)
    
    dut.start.value = 1
    await RisingEdge(dut.clk) # Edge: ALU samples 'start'
    dut.start.value = 0

    await Timer(1, unit="ps")
    
    while dut.u_alu.busy.value == 1:
        await RisingEdge(dut.clk)
    
    await ReadOnly()
    
    actual_val = int(dut.result.value)
    assert actual_val == 12, f"Expected 12, got {actual_val}"

@cocotb.test()
async def test_multi_cycle_div(dut):
    await setup_dut(dut)
    
    assert dut.u_alu.busy.value == 0, "ALU was busy before test started!"
    
    dut.A.value = 100
    dut.B.value = 10
    dut.opcode.value = 9
    dut.diss_clk.value = 0
    
    await RisingEdge(dut.clk)
    
    dut.start.value = 1
    await RisingEdge(dut.clk) 
    dut.start.value = 0

    await Timer(1, unit="ps")
    
    while dut.u_alu.busy.value == 1:
        await RisingEdge(dut.clk)
    
    await ReadOnly()
    assert int(dut.result.value) == 10, f"Expected 10, got {int(dut.result.value)}"

def test_alu_runner():
    import os
    from pathlib import Path
    from cocotb_tools.runner import get_runner

    sim = os.getenv("SIM", "icarus")
    proj_path = Path(__file__).resolve().parent.parent

    sources = [
        proj_path / "sources" / "alu.v",
        proj_path / "sources" / "alu_clk_off.v",
        proj_path / "sources" / "top.v",
    ]

    runner = get_runner(sim)
    runner.build(sources=sources, hdl_toplevel="top", always=True)
    runner.test(hdl_toplevel="top", test_module="test_alu_hidden")
