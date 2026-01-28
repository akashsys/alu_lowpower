import re
import argparse
import os

def swap_cell(instance_name, new_cell_type, netlist_path):
    # Verify file existence
    if not os.path.exists(netlist_path):
        print(f"ERROR: Netlist not found at {netlist_path}")
        return

    # Read the netlist
    with open(netlist_path, 'r') as f:
        content = f.read()

    # Regex: Look for [CellType] followed by [InstanceName] and an opening parenthesis
    # Example match: sky130_fd_sc_hd__o311ai_0 _5748_ (
    pattern = rf"(\w+)\s+{instance_name}\s*\("
    
    if not re.search(pattern, content):
        print(f"ERROR: Instance {instance_name} not found in {netlist_path}!")
        return

    # Replace old cell type with the new one
    # We keep the instance name and the start of the pin connections exactly the same
    new_content = re.sub(pattern, rf"{new_cell_type} {instance_name} (", content)

    # Write the updated netlist back to the same file
    with open(netlist_path, 'w') as f:
        f.write(new_content)
    
    print(f"SUCCESS: Swapped {instance_name} to {new_cell_type} in {netlist_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PHINITY surgical ECO tool")
    
    # Instance name to find (e.g., _5748_)
    parser.add_argument("--instance", required=True)
    
    # Target cell type to swap to (e.g., sky130_fd_sc_hd__o311ai_1)
    parser.add_argument("--new_cell", required=True)
    
    # Since the script is in 'sources/', the default netlist name is just 'netlist.v'
    parser.add_argument("--file", default="netlist.v")
    
    args = parser.parse_args()
    swap_cell(args.instance, args.new_cell, args.file)