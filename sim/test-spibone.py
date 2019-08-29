# Tests for Wishbone-over-SPI
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, NullTrigger, Timer
from cocotb.result import TestFailure, TestSuccess, ReturnValue

from wishbone import WishboneMaster, WBOp

import logging
import csv

# Disable pylint's E1101, which breaks on our wishbone addresses
#pylint:disable=E1101

class SpiboneTest:
    def __init__(self, dut):
        self.dut = dut
        self.csrs = dict()
        with open("csr.csv", newline='') as csr_csv_file:
            csr_csv = csv.reader(csr_csv_file)
            # csr_register format: csr_register, name, address, size, rw/ro
            for row in csr_csv:
                if row[0] == 'csr_register':
                    exec("self.{} = {}".format(row[1].upper(), int(row[2], base=0)))
                    # self.csrs[row[1]] = int(row[2], base=0)
        cocotb.fork(Clock(dut.clk48, 20800, 'ps').start())
        self.wb = WishboneMaster(dut, "wishbone", dut.clk12, timeout=20)

        # Set the signal "test_name" to match this test, so that we can
        # tell from gtkwave which test we're in.
        import inspect
        tn = cocotb.binary.BinaryValue(value=None, n_bits=4096)
        tn.buff = inspect.stack()[1][3]
        self.dut.test_name = tn

    @cocotb.coroutine
    def write(self, addr, val):
        yield self.wb.write(addr, val)

    @cocotb.coroutine
    def read(self, addr):
        value = yield self.wb.read(addr)
        raise ReturnValue(value)

    @cocotb.coroutine
    def reset(self):
        self.dut.reset = 1
        yield RisingEdge(self.dut.clk12)
        self.dut.reset = 0
        yield RisingEdge(self.dut.clk12)

@cocotb.test()
def test_wishbone_write(dut):
    harness = SpiboneTest(dut)
    yield harness.reset()
    yield harness.write(0x40000000, 0x12345678)
    val = yield harness.read(0x40000000)
    if val != 0x12345678:
        raise TestFailure("memory check failed -- expected 0x12345678, got 0x{:08x}".format(val))

    yield harness.write(harness.CTRL_SCRATCH, 0x54)
    val = yield harness.read(harness.CTRL_SCRATCH)
    if val != 0x54:
        raise TestFailure("wishbone check failed -- expected 0x54, got 0x{:02x}".format(val))
