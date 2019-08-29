# Tests for Wishbone-over-SPI
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, NullTrigger, Timer
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
        yield RisingEdge(self.dut.clk12)
        self.dut.reset = 0
        self.spi_mosi = 0
        self.spi_clk = 0
        self.spi_cs_n = 1
        yield RisingEdge(self.dut.clk12)

    @cocotb.coroutine
    def host_spi_tick(self):
        self.dut.spi_clk = 0
        yield FallingEdge(self.dut.clk12)
        self.dut.spi_clk = 1
        yield RisingEdge(self.dut.clk12)

    @cocotb.coroutine
    def host_spi_write_byte(self, val):
        for shift in range(0, 8):
            self.dut.spi_mosi = (val >> (7-shift)) & 1
            yield self.host_spi_tick()

    @cocotb.coroutine
    def host_spi_write(self, addr, val):
        self.dut.spi_cs_n = 0
        self.dut.spi_mosi = 0

        # Header
        # 0: Write
        # 1: Read
        yield self.host_spi_write_byte(0)

        # Address
        for shift in [24, 16, 8, 0]:
            yield self.host_spi_write_byte(addr >> shift)

        # Value
        for shift in [24, 16, 8, 0]:
            yield self.host_spi_write_byte(val >> shift)

        # Wait for response
        timeout_counter = 0
        while True:
            if self.dut.spi_miso == 0:
                break
            yield self.host_spi_tick()
            timeout_counter = timeout_counter + 1
            if timeout_counter > 200:
                raise TestFailure("timed out waiting for response")
        self.dut.spi_cs_n = 1

    @cocotb.coroutine
    def host_spi_read(self, addr):
        self.dut.spi_cs_n = 0
        self.dut.spi_mosi = 0

        # Header
        # 0: Write
        # 1: Read
        yield self.host_spi_write_byte(1)

        # Address
        for shift in [24, 16, 8, 0]:
            yield self.host_spi_write_byte(addr >> shift)

        # Wait for response
        timeout_counter = 0
        while True:
            if self.dut.spi_miso == 0:
                break
            yield self.host_spi_tick()
            timeout_counter = timeout_counter + 1
            if timeout_counter > 200:
                raise TestFailure("timed out waiting for response")

        for i in range(0, 8):
            if self.dut.spi_miso != 0:
                raise TestFailure("spi_miso was not 0 during response header")
            yield self.host_spi_tick()

        # Value
        val = 0
        for shift in range(31, -1, -1):
            val = val | (int(self.dut.spi_miso) << shift)
            yield self.host_spi_tick()

        self.dut.spi_cs_n = 1
        raise ReturnValue(val)

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

@cocotb.coroutine
def test_spibone_write(dut, canary):
    addr = 0x40000004
    harness = SpiboneTest(dut)
    yield harness.reset()
    yield harness.host_spi_write(addr, canary)
    check_canary = yield harness.read(addr)
    if check_canary != canary:
        raise TestFailure("check_canary 0x{:08x} doesn't match written value 0x{:08x}".format(check_canary, canary))

@cocotb.coroutine
def test_spibone_read(dut, canary):
    addr = 0x40000004
    harness = SpiboneTest(dut)
    yield harness.reset()

    yield harness.write(addr, canary)
    check_canary = yield harness.host_spi_read(addr)
    if check_canary != canary:
        raise TestFailure("check_canary 0x{:08x} doesn't match written value 0x{:08x}".format(check_canary, canary))

@cocotb.test()
def test_spibone_read_aaaaaaaa(dut):
    yield test_spibone_read(dut, 0xaaaaaaaa)

@cocotb.test()
def test_spibone_read_55555555(dut):
    yield test_spibone_read(dut, 0x55555555)

@cocotb.test()
def test_spibone_write_aaaaaaaa(dut):
    yield test_spibone_write(dut, 0xaaaaaaaa)

@cocotb.test()
def test_spibone_write_55555555(dut):
    yield test_spibone_write(dut, 0x55555555)