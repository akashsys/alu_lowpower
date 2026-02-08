import os
import re
import subprocess
import pytest
from pathlib import Path
from cocotb_tools.runner import get_runner
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import uuid
import time
import tempfile
import shutil
import atexit

# --- WINDOWS DOCKER CONFIG ---
# Force use of the TCP bridge you enabled in Docker Desktop
os.environ["DOCKER_HOST"] = "tcp://localhost:2375"

if "ACTIVE_CONTAINER_ID" not in os.environ:
    os.environ["ACTIVE_CONTAINER_ID"] = f"openlane_{os.getpid()}_{uuid.uuid4().hex[:8]}"

CONTAINER_ID = os.environ["ACTIVE_CONTAINER_ID"]
def get_dynamic_container_path(state_file_override=None):
    """Get unique task path with high-resolution timestamp to prevent collisions"""
    if state_file_override:
        state_file = state_file_override
    else:
        # Check if we are in an isolated parallel job
        base_dir = os.getenv("ISOLATED_SOURCES")
        if base_dir:
            state_file = Path(base_dir).resolve() / ".task_dir"
        else:
            # Standard fallback
            test_dir = Path(__file__).resolve().parent
            state_file = test_dir.parent / "sources" / ".task_dir"
    
    if state_file.exists():
        path = state_file.read_text().strip()
        if path:
            return path
            
    # Generate unique path with nanosecond timestamp + PID + UUID
    # This prevents collisions even with simultaneous starts
    timestamp_ns = int(time.time() * 1e9)
    pid = os.getpid()
    unique_id = uuid.uuid4().hex[:8]
    task_id = f"task_{timestamp_ns}_{pid}_{unique_id}"
    
    # Write to state file for this process
    task_path = f"/openlane/{task_id}"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(task_path)
    
    return task_path


# ==============================================================================
# 1. THE PYTEST RUNNER
# ==============================================================================
def test_vlsi_signoff_runner():
    """Orchestrates sync and Cocotb simulation."""
    # os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:2375"
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    
    sim = os.getenv("SIM", "icarus")
    
    # --- DYNAMIC PATH DISCOVERY ---
    # Look for the sandbox path exported by the bash script
    base_dir = os.getenv("ISOLATED_SOURCES")
    if base_dir:
        sources_dir = Path(base_dir).resolve()
        # In the sandbox, .task_dir is directly inside sources/
        state_file = sources_dir / ".task_dir"
    else:
        # Fallback for manual local runs
        proj_path = Path(__file__).resolve().parent.parent 
        sources_dir = proj_path / "sources"
        state_file = sources_dir / ".task_dir"

    # Resolve dynamic path for this specific agent task
    # (Pass the state_file path to your helper if needed)
    current_task_path = get_dynamic_container_path(state_file)

    # --- Step 1: Ensure unique container exists ---
    print(f"\n>>> Using unique container: {CONTAINER_ID}")
    print(f">>> Task path: {current_task_path}")
    
    # Check if this specific container exists
    result = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={CONTAINER_ID}"],
        capture_output=True,
        text=True
    )
    
    if not result.stdout.strip():
        print(f">>> Creating new container: {CONTAINER_ID}")
        subprocess.run([
            "docker", "run", "-d", 
            "--name", CONTAINER_ID,
            "efabless/openlane:latest",
            "tail", "-f", "/dev/null"
        ], check=True)
    
    # --- Step 2: Sync to Docker ---
    print(f"\nSyncing to Docker container {CONTAINER_ID} at {current_task_path}...")
    subprocess.run(["docker", "exec", CONTAINER_ID, "mkdir", "-p", current_task_path], check=True)
    subprocess.run(f"docker cp \"{sources_dir}/.\" {CONTAINER_ID}:{current_task_path}/", shell=True, check=True)

    # --- Step 3: Setup Cocotb Runner ---
    netlist_path = sources_dir / "netlist.v"
    rtl_path = sources_dir / "elastic_credit_arbiter.v"

    if not netlist_path.exists():
        print(">>> [INIT] Netlist not found. Generating initial baseline netlist...")
        # Execute the synthesis portion ONLY
        subprocess.run([
            "docker", "exec", CONTAINER_ID, "bash", "-c", 
            f"cd {current_task_path} && yosys -s syn_script.ys"
        ], check=True)
        # Pull it to host so the runner can build the simulation
        subprocess.run([
            "docker", "cp", f"{CONTAINER_ID}:{current_task_path}/netlist.v", str(netlist_path)
        ], check=True)
    else:
        print(">>> [SKIP] Netlist exists. Using current version for testing.")

    #sources = [netlist_path]
    sources = [rtl_path]
    runner = get_runner(sim)

    runner.build(
        sources=sources,
        hdl_toplevel="elastic_credit_arbiter",
        always=True,
        build_args=[
            f"-y{sources_dir}/cells/base",
            f"-y{sources_dir}/cells/strength", 
            f"-y{sources_dir}/models",          
            f"-I{sources_dir}/cells/base",      
            f"-I{sources_dir}/models",   
            "-Y.v",     
            "-grelative-include",
        ]
    )    

    runner.test(
        hdl_toplevel="elastic_credit_arbiter",
        test_module=Path(__file__).stem,
        extra_env={"ACTIVE_CONTAINER_ID": CONTAINER_ID}
    )

# ==============================================================================
# 2. THE COCOTB TESTS (VLSI Sign-off Checks)
# ==============================================================================

@cocotb.test()
async def test_wns_slack(dut):
    """Cocotb Test: Worst Negative Slack check via Dynamic Docker Path"""
    #os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:2375"
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    current_task_path = get_dynamic_container_path()
    WNS_TARGET = 0
    
    # Create unique temp directory for this test instance (prevents file conflicts)
    test_tmpdir = tempfile.mkdtemp(prefix=f"test_timing_{os.getpid()}_")
    
    try:
        dut._log.info(f"Analyzing Timing in: {current_task_path}")
        dut._log.info(f"Using container: {CONTAINER_ID}")
        dut._log.info(f"Temp directory: {test_tmpdir}")

        # --- Step 1: Execute STA ---
        # We use the dynamic path resolved from .task_dir
        cmd = ["docker", "exec", CONTAINER_ID, "bash", "-c", 
               f"cd {current_task_path} && sta -no_init run_sta.tcl"]
        subprocess.run(cmd, check=True)

        # --- Step 2: Copy report to unique location ---
        timing_rpt = os.path.join(test_tmpdir, "timing_report.rpt")
        subprocess.run(
            f"docker cp {CONTAINER_ID}:{current_task_path}/timing_report.rpt \"{timing_rpt}\"", 
            shell=True, check=True
        )

        # --- Step 3: Parse and Validate ---
        with open(timing_rpt, "r") as f:
            report_content = f.read()

        all_slacks = re.findall(r"([-+]?[\d\.]+)\s+slack", report_content)

        if all_slacks:
            wns = min(float(s) for s in all_slacks)
            status_msg = f"WNS is {wns}ns (Target: >= {WNS_TARGET}ns)"
            
            if wns >= WNS_TARGET:
                dut._log.info(f"TIMING MET: {status_msg}")
            else:
                dut._log.error(f"TIMING VIOLATED: {status_msg}")

            assert wns >= WNS_TARGET, f"Timing check failed: {status_msg}"
        else:
            raise RuntimeError("Slack not found in report.")
    
    finally:
        # Cleanup temp directory
        shutil.rmtree(test_tmpdir, ignore_errors=True)

@cocotb.test()
async def test_area_constraint(dut):
    """Cocotb Test: Chip Area check via script.ys and report extraction"""
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    current_task_path = get_dynamic_container_path()
    AREA_CEILING = 10556.0
    
    # Create unique temp directory for this test instance (prevents file conflicts)
    test_tmpdir = tempfile.mkdtemp(prefix=f"test_area_{os.getpid()}_")
    
    try:
        dut._log.info(f"Analyzing Area in: {current_task_path}")
        dut._log.info(f"Using container: {CONTAINER_ID}")
        dut._log.info(f"Temp directory: {test_tmpdir}")

        # --- Step 1: Execute Yosys using the .ys script ---
        # This generates the area.rpt inside the container
        cmd = ["docker", "exec", CONTAINER_ID, "bash", "-c", 
               f"cd {current_task_path} && yosys area.ys"]
        subprocess.run(cmd, check=True)

        # --- Step 2: Copy report to unique location ---
        # Parity with timing_report.rpt logic
        area_rpt = os.path.join(test_tmpdir, "area.rpt")
        subprocess.run(
            f"docker cp {CONTAINER_ID}:{current_task_path}/area.rpt \"{area_rpt}\"", 
            shell=True, check=True
        )

        # --- Step 3: Parse and Validate ---
        with open(area_rpt, "r") as f:
            report_content = f.read()

        # Capture the area number
        area_match = re.search(r"Chip area.*:\s*([\d\.]+)", report_content)

        if area_match:
            current_area = float(area_match.group(1))
            current_area_rd = round(current_area, 3)
            status_msg = f"Area is {current_area_rd} um^2 (Target: <= {AREA_CEILING})"
            
            if current_area_rd <= AREA_CEILING:
                dut._log.info(f"AREA MET: {status_msg}")
            else:
                dut._log.error(f"AREA VIOLATED: {status_msg}")

            assert current_area_rd <= AREA_CEILING, f"Area check failed: {status_msg}"
        else:
            # Debugging aid: show what the file actually contains if parsing fails
            dut._log.error(f"Regex failed. Report snippet:\n{report_content[-200:]}")
            raise RuntimeError("Area data not found in area.rpt.")
    
    finally:
        # Cleanup temp directory
        shutil.rmtree(test_tmpdir, ignore_errors=True)



# ==============================================================================
# 3. FUNCTIONAL TESTS (Hardware Logic)
# ==============================================================================

async def reset_dut(dut):
    dut.rst_n.value = 0
    await Timer(10, unit="ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_1_fixed_priority(dut):
    """Functional Check 1: Fixed Priority (Port 0 > Port 3)."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # --- 1. Fixed Priority Check ---
    dut.packet_size.value = 0x10
    dut.request.value = 0b1001 
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.grant.value == 0b0001, f"Port 0 should win via fixed priority. Got {dut.grant.value}"
    dut._log.info("Fixed Priority Verified.")

@cocotb.test()
async def test_2_starvation_escalation(dut):
    """Functional Check 2: Starvation Escalation and Tier Hierarchy."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # --- 2. Starvation Escalation Check ---
    dut._log.info("Stalling both Port 0 and Port 3 to reach Tier 1...")
    dut.request.value = 0b1001
    
    # Wait for both to age past 32 cycles (AGE_THRESH)
    for _ in range(40): 
        await RisingEdge(dut.clk)
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    
    # SPEC VALIDATION: Both are Tier 1 (Aged). 
    # Port 0 has fixed priority over Port 3, so Port 0 MUST win.
    dut._log.info(f"Checking winner in Tier 1. Current grant: {dut.grant.value}")
    assert dut.grant.value == 0b0001, f"Spec Violation: Port 0 should win Tier 1. Got {dut.grant.value}"

    # --- 2b. Verify Port 3 can win Tier 1 if Port 0 is served ---
    dut._log.info("Dropping Port 0 to see if Port 3 is still in Tier 1...")
    dut.request.value = 0b1000 # Only Port 3 remains
    
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    
    # Now Port 3 should win immediately because it is already aged
    assert dut.grant.value == 0b1000, f"Port 3 failed to win after Port 0 released. Got {dut.grant.value}"
    dut._log.info("Starvation Tier Hierarchy Verified.")

# ==============================================================================
# 3. FUNCTIONAL TESTS (Hardware Logic)
# ==============================================================================

async def reset_dut(dut):
    """Resets the DUT and ensures a clean starting state for every test."""
    dut.rst_n.value = 0
    await Timer(10, unit="ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

@cocotb.test()
async def test_1_fixed_priority(dut):
    """Functional Check 1: Fixed Priority (Port 0 > Port 3)."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.packet_size.value = 0x10
    dut.request.value = 0b1001 
    for _ in range(3): await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    
    assert dut.grant.value == 0b0001, f"Port 0 should win via fixed priority. Got {dut.grant.value}"
    dut._log.info("Fixed Priority Verified.")

@cocotb.test()
async def test_2_starvation_escalation(dut):
    """Functional Check 2: Starvation Escalation and Tier Hierarchy."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut._log.info("Stalling both Port 0 and Port 3 to reach Tier 1...")
    dut.request.value = 0b1001
    
    # Age the requests past the threshold (32 cycles)
    for _ in range(40): await RisingEdge(dut.clk)
    
    await Timer(1, unit="ns")
    assert dut.grant.value == 0b0001, f"Spec Violation: Port 0 should win Tier 1. Got {dut.grant.value}"

    dut._log.info("Dropping Port 0 to see if Port 3 is still in Tier 1...")
    dut.request.value = 0b1000 
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    
    assert dut.grant.value == 0b1000, f"Port 3 failed to win after Port 0 released. Got {dut.grant.value}"
    dut._log.info("Starvation Tier Hierarchy Verified.")

@cocotb.test()
async def test_3_credit_exhaustion(dut):
    """Functional Check 3: Credit Guard (Request > Available)."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # --- SELF-CONTAINED SETUP ---
    # To test exhaustion, we request a packet LARGER than the bucket (0x80)
    # This proves the guard works even when the bucket is full.
    dut.packet_size.value = 0x85 
    dut.request.value = 0b0001 
    
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    
    # Grant should be 0 because 0x85 > 0x80 max credits
    assert dut.grant_valid.value == 0, f"Error: Grant issued for 0x85 packet despite 0x80 limit."
    dut._log.info("Credit Guard Verified.")

@cocotb.test()
async def test_4_elastic_increment(dut):
    """Functional Check 4: Elasticity (Refill allows previously blocked grant)."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # 1. Drain credits first by taking a large grant
    dut.packet_size.value = 0x70
    dut.request.value = 0b0001
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk) # Credit is now very low (~0x10)

    # 2. Verify a new request for 0x50 is blocked
    dut.packet_size.value = 0x50
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.grant_valid.value == 0, "Packet should be blocked due to low credits."

    # 3. Idle for 100 cycles to allow "Elastic" refill
    dut.request.value = 0x0
    for _ in range(100): await RisingEdge(dut.clk)

    # 4. Now the 0x50 packet should pass
    dut.request.value = 0b0001
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    
    assert dut.grant.value == 0b0001, f"Elasticity failed. Refill did not allow grant. Got {dut.grant.value}"
    dut._log.info("Elasticity and Port 0 Priority Verified.")


# ==============================================================================
# 4. CLEANUP HANDLER
# ==============================================================================

def cleanup_container():
    """Cleanup this test's unique container"""
    print(f"\n>>> Cleaning up container: {CONTAINER_ID}")
    try:
        subprocess.run(
            ["docker", "stop", CONTAINER_ID], 
            stderr=subprocess.DEVNULL, 
            timeout=10,
            check=False
        )
        subprocess.run(
            ["docker", "rm", CONTAINER_ID], 
            stderr=subprocess.DEVNULL, 
            timeout=10,
            check=False
        )
        print(f">>> Container {CONTAINER_ID} cleaned up successfully")
    except Exception as e:
        print(f">>> Warning: Container cleanup failed: {e}")

# Register cleanup on exit
atexit.register(cleanup_container)