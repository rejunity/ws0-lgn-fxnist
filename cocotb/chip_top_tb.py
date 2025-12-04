# SPDX-FileCopyrightText: © 2025 Project Template Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import random
import logging
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, Edge, RisingEdge, FallingEdge, ClockCycles
from cocotb_tools.runner import get_runner

sim = os.getenv("SIM", "icarus")
pdk_root = os.getenv("PDK_ROOT", Path("~/.ciel").expanduser())
pdk = os.getenv("PDK", "gf180mcuD")
scl = os.getenv("SCL", "gf180mcu_fd_sc_mcu7t5v0")
gl = os.getenv("GL", False)
slot = os.getenv("SLOT", "1x1")

hdl_toplevel = "chip_top"


#########################################################################################################################
import numpy as np

WRITE_ENABLE  = 512
WRITE_DISABLE = 0

gates_value = os.getenv('GATES')
GATE_LEVEL_SIMULATION = not gates_value in (None, "no")
print("GATES", GATE_LEVEL_SIMULATION)

CLEAR_BETWEEN_TEST_SAMPLES = False
# CLEAR_BETWEEN_TEST_SAMPLES = True
# CLEAR_WITH_ALTERNATING_PATTERN = False
CLEAR_WITH_ALTERNATING_PATTERN = True

SEVEN_SEGMENT = True


X = \
[[0] * 256,
 [1] * 256]


Y = "../src/20251204-053837_binTestAcc7780_seed521734_epochs2_2x8000_b256_lr75_interconnect.npz"
###############################################################################

def split_array(lst, chunk_size=8):
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def array_to_bin(arr):
    if isinstance(arr, list):
        arr = np.array(arr)
    return ''.join(arr.astype(int).astype(str))

def seven_segment_inverse(segment):
    segment_to_digit = {
        0b0111111: 0,
        0b0000110: 1,
        0b1011011: 2,
        0b1001111: 3,
        0b1100110: 4,
        0b1101101: 5,
        0b1111100: 6,
        0b0000111: 7,
        0b1111111: 8,
        0b1100111: 9
    }
    if isinstance(segment, str):
        segment = int(segment, 2)
    return segment_to_digit.get(segment, None)

def assert_output(dut, y):
    does_y_containt_already_summed_values = len(y) == 0 and y[0] > 0
    if not does_y_containt_already_summed_values and \
       not GATE_LEVEL_SIMULATION: # Gate level simulation prevents to check the output
                                  # of the network, but do it when we can for extra testing
        # network output wire array might be larger than the output in the dataset
        # take only first bits (in string format)
        # assert str(dut.tt_um_rejunity_lgn_mnist.y.value)[::-1].startswith(array_to_bin(y))
        assert str(dut.i_chip_core.lgn.y.value)[::-1].startswith(array_to_bin(y))

    categories = np.sum(y.reshape(10, -1), -1)
    print(categories)

    expected = len(categories) - 1 - np.argmax(categories[::-1])
    if SEVEN_SEGMENT:
        computed = seven_segment_inverse(dut.bidir_PAD.value.to_unsigned() & 127)
    else:
        computed = dut.bidir_PAD.value.to_unsigned() & 15
    dut._log.info(f"Expected category: {expected}")
    dut._log.info(f"Computed category: {computed}")

    assert expected == computed

    expected = int(categories[expected]) // 2
    computed = (dut.bidir_PAD.value.to_unsigned() >> 8) & 255
    dut._log.info(f"Expected value: {expected}")
    dut._log.info(f"Computed value: {computed}")

    assert expected == computed

#########################################################################################################################

async def set_defaults(dut):
    dut.input_PAD.value = 0

async def enable_power(dut):
    dut.VDD.value = 1
    dut.VSS.value = 0

async def start_clock(clock, freq=1):
    """Start the clock @ freq MHz"""
    c = Clock(clock, 1 / freq * 1000, "ns")
    cocotb.start_soon(c.start())


async def reset(reset, active_low=True, time_ns=1000):
    """Reset dut"""
    cocotb.log.info("Reset asserted...")

    reset.value = not active_low
    await Timer(time_ns, "ns")
    reset.value = active_low

    cocotb.log.info("Reset deasserted.")


async def start_up(dut):
    """Startup sequence"""
    await set_defaults(dut)
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD)
    await reset(dut.rst_n_PAD)

@cocotb.test()
async def test_lgn(dut):
    global X, Y
    if isinstance(Y, str):
        data = np.load("../" + Y)
        X = data["input"]
        Y = data["output"]
        print("Test dataset: ", X.shape, Y.shape)


    # Create a logger for this testbench
    logger = logging.getLogger("my_testbench")
    logger.info("Startup sequence...")

    # Start up
    await start_up(dut)
    logger.info("Running the test...")

    # Wait for some time...
    await ClockCycles(dut.clk_PAD, 10)

    # dut.input_PAD.value = 0 | WRITE_ENABLE
    # await ClockCycles(dut.clk_PAD, 256//8)

    logger.info("Test network")
    print("test network starts")
    # Set the input values you want to test
    alt = 0
    for x, y in zip(X[:8], Y[:8]): # dataset can contain a lot of test samples
                                   # take only 8 for tractable speed of the test
        x = x[::-1] # reverse input data for uploading via the shift register
        logger.info(f"Input: {array_to_bin(x)}")
        logger.info("Clear input buffer")
        dut.input_PAD.value = ( 0 if alt == 0 else 255) | WRITE_ENABLE
        def category_index(): return dut.bidir_PAD.value.to_unsigned() & 15 if (not SEVEN_SEGMENT) else seven_segment_inverse(dut.bidir_PAD.value.to_unsigned() & 127)
        def category_value(): return (dut.bidir_PAD.value.to_unsigned() >> 8) & 255
        if CLEAR_BETWEEN_TEST_SAMPLES:
            for i in range(256//8): # TODO: fix dimensions
                if i % 2 == 1:
                    if alt == 0:
                        print(f"0000000000000000 best index: {category_index()} value: {category_value()}")
                    else:
                        print(f"1111111111111111 best index: {category_index()} value: {category_value()}")
                await ClockCycles(dut.clk_PAD, 1)
            alt = 1-alt if CLEAR_WITH_ALTERNATING_PATTERN else alt

        logger.info(f"Set input buffer, {len(x)} bits")
        i = 0
        for block_of_8 in split_array(x, 8):
            print(array_to_bin(block_of_8), end="")
            if i % 2 == 1:
                print(f" best index: {category_index()} value: {category_value()}")
            dut.input_PAD.value = int(array_to_bin(block_of_8), 2)
            await ClockCycles(dut.clk_PAD, 1)
            i += 1

        dut.input_PAD.value = 0 | WRITE_DISABLE
        await ClockCycles(dut.clk_PAD, 1)
        logger.info(f"Computed best index: {category_index()} value: {category_value()}")

        logger.info(f"Expected output of the last layer: {array_to_bin(y)}")

        assert_output(dut, y)

    logger.info("Done!")

# # @cocotb.test()
# async def test_counter(dut):
#     """Run the counter test"""

#     # Create a logger for this testbench
#     logger = logging.getLogger("my_testbench")

#     logger.info("Startup sequence...")

#     # Start up
#     await start_up(dut)

#     logger.info("Running the test...")

#     # Wait for some time...
#     await ClockCycles(dut.clk_PAD, 10)

#     # Start the counter by setting all inputs to 1
#     dut.input_PAD.value = 1

#     # Wait for a number of clock cycles
#     print("Running 2 cycles of the LGN inference, this might take some time!")
#     await ClockCycles(dut.clk_PAD, 2)

#     # # Check the end result of the counter
#     # assert dut.bidir_PAD.value == 100 - 1

#    logger.info("Done!")


def chip_top_runner():
    proj_path = Path(__file__).resolve().parent

    sources = []
    defines = {f"SLOT_{slot.upper()}": True}
    includes = [proj_path / "../src/"]

    if gl:
        # SCL models
        sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / f"{scl}.v")
        sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / "primitives.v")

        # We use the powered netlist
        sources.append(proj_path / f"../final/pnl/{hdl_toplevel}.pnl.v")

        defines = {"FUNCTIONAL": True, "USE_POWER_PINS": True}
    else:
        sources.append(proj_path / "../src/chip_top.sv")
        sources.append(proj_path / "../src/chip_core.sv")
        sources.append(proj_path / "../src/lgn.v")
        sources.append(proj_path / "../src/net.v")

    sources += [
        # IO pad models
        Path(pdk_root) / pdk / "libs.ref/gf180mcu_fd_io/verilog/gf180mcu_fd_io.v",
        Path(pdk_root) / pdk / "libs.ref/gf180mcu_fd_io/verilog/gf180mcu_ws_io.v",
        
        # SRAM macros
        Path(pdk_root) / pdk / "libs.ref/gf180mcu_fd_ip_sram/verilog/gf180mcu_fd_ip_sram__sram512x8m8wm1.v",
        
        # Custom IP
        proj_path / "../ip/gf180mcu_ws_ip__id/vh/gf180mcu_ws_ip__id.v",
        proj_path / "../ip/gf180mcu_ws_ip__logo/vh/gf180mcu_ws_ip__logo.v",
    ]

    build_args = []

    if sim == "icarus":
        # For debugging
        # build_args = ["-Winfloop", "-pfileline=1"]
        pass

    if sim == "verilator":
        build_args = ["--timing", "--trace", "--trace-fst", "--trace-structs"]

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        defines=defines,
        always=True,
        includes=includes,
        build_args=build_args,
        waves=True,
    )

    plusargs = []

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module="chip_top_tb,",
        plusargs=plusargs,
        waves=True,
    )


if __name__ == "__main__":
    chip_top_runner()
