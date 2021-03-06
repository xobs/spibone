# Tests for Wishbone-over-SPI
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Edge, NullTrigger, Timer
from cocotb.result import TestFailure, TestSuccess, ReturnValue

from wishbone import WishboneMaster, WBOp

import logging
import csv
import inspect
import os

# Disable pylint's E1101, which breaks on our wishbone addresses
#pylint:disable=E1101

class SpiboneTest:
    def __init__(self, dut, test_name):
        if "WIRES" in os.environ:
            self.wires = int(os.environ["WIRES"])
        else:
            self.wires = 4
        self.dut = dut
        self.test_name = test_name
        self.csrs = dict()
        self.dut.reset = 1
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
        tn = cocotb.binary.BinaryValue(value=None, n_bits=4096)
        tn.buff = test_name
        self.dut.test_name = tn

    @cocotb.coroutine
    # Validate that the MOSI line doesn't change while CLK is 1
    def validate_mosi_stability(self, test_name):
        previous_clk = self.dut.spi_clk
        previous_val = self.dut.spi_mosi
        while True:
            v = self.dut.spi_cs_n.value
            v_str = "{}".format(v)
            # self.dut._log.error("{} - CS_N value: {}  Reset value: {}".format(test_name, v_str, self.dut.reset))
            if v_str == "0" and self.dut.reset == 0:
                if self.dut.spi_clk:
                    # Clock went high, so capture value
                    if previous_clk == 0:
                        previous_val = self.dut.spi_mosi
                    else:
                        if int(self.dut.spi_mosi) != int(previous_val):
                            raise TestFailure("spi.mosi changed while clk was high (was {}, now {})".format(previous_val, self.dut.spi_mosi))
                previous_clk = self.dut.spi_clk
            # else:
            #     self.dut._log.error("CS_N is Z")
            yield Edge(self.dut.clk48)

    @cocotb.coroutine
    # Validate that the MOSI and MISO line don't change while CLK is 1
    def validate_mosi_miso_stability(self, test_name):
        previous_clk = self.dut.spi_clk
        previous_mosi = self.dut.spi_mosi
        if self.wires == 4:
            previous_miso = self.dut.spi_miso
        while True:
            v = self.dut.spi_cs_n.value
            v_str = "{}".format(v)
            # self.dut._log.error("{} - CS_N value: {}  Reset value: {}".format(test_name, v_str, self.dut.reset))
            if v_str == "0" and self.dut.reset == 0:
                if self.dut.spi_clk:
                    # Clock went high, so capture value
                    if previous_clk == 0:
                        previous_mosi = self.dut.spi_mosi
                        if self.wires == 4:
                            previous_miso = self.dut.spi_miso
                    else:
                        if int(self.dut.spi_mosi) != int(previous_mosi):
                            raise TestFailure("spi.mosi changed while clk was high (was {}, now {})".format(previous_mosi, self.dut.spi_mosi))
                        if self.wires == 4:
                            if int(self.dut.spi_miso) != int(previous_miso):
                                raise TestFailure("spi.mosi changed while clk was high (was {}, now {})".format(previous_miso, self.dut.spi_miso))
                previous_clk = self.dut.spi_clk
            # else:
            #     self.dut._log.error("CS_N is Z")
            yield Edge(self.dut.clk48)

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
        self.dut.spi_cs_n = 1
        self.dut.spi_mosi = 0
        self.dut.spi_clk = 0
        yield RisingEdge(self.dut.clk12)
        yield RisingEdge(self.dut.clk12)
        cocotb.fork(self.validate_mosi_miso_stability(self.test_name))
        self.dut.reset = 0
        self.dut.spi_mosi = 0
        self.dut.spi_clk = 0
        self.dut.spi_cs_n = 1
        yield RisingEdge(self.dut.clk12)
        yield RisingEdge(self.dut.clk12)

    @cocotb.coroutine
    def host_spi_tick(self):
        self.dut.spi_clk = 0
        yield RisingEdge(self.dut.clk12)
        self.dut.spi_clk = 1
        yield RisingEdge(self.dut.clk12)

    @cocotb.coroutine
    def host_spi_write_byte(self, val):
        for shift in range(7, -1, -1):
            self.dut.spi_mosi = (val >> shift) & 1
            yield self.host_spi_tick()

    @cocotb.coroutine
    def host_spi_read_byte(self):
        val = 0
        for shift in range(7, -1, -1):
            yield self.host_spi_tick()
            if self.wires == 3 or self.wires == 2:
                val = val | (int(self.dut.spi_mosi) << shift)
            elif self.wires == 4:
                val = val | (int(self.dut.spi_miso) << shift)
        raise ReturnValue(val)

    @cocotb.coroutine
    def host_start(self):
        if self.wires == 3 or self.wires == 4:
            self.dut.spi_cs_n = 0
            self.dut.spi_mosi = 0
        elif self.wires == 2:
            yield self.host_spi_write_byte(0xab)
        if False:
            yield

    @cocotb.coroutine
    def host_finish(self):
        if self.wires == 3 or self.wires == 4:
            self.dut.spi_cs_n = 1
        self.dut.spi_mosi = 0
        yield self.host_spi_tick()
        self.dut.spi_mosi = 0
        yield self.host_spi_tick()
        self.dut.spi_mosi = 0
        yield self.host_spi_tick()
        self.dut.spi_mosi = 0
        yield self.host_spi_tick()
        self.dut.spi_mosi = 0
        yield self.host_spi_tick()
        if False:
            yield

    @cocotb.coroutine
    def host_spi_write(self, addr, val):
        yield self.host_start()

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
            val = yield self.host_spi_read_byte()
            if val != 0xff:
                if val == 0:
                    break
                raise TestFailure("response byte was 0x{:02x}, not 0x00".format(val))
            timeout_counter = timeout_counter + 1
            if timeout_counter > 20:
                raise TestFailure("timed out waiting for response")
        yield self.host_finish()

    @cocotb.coroutine
    def host_spi_read(self, addr):
        yield self.host_start()

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
            val = yield self.host_spi_read_byte()
            if val != 0xff:
                if val == 1:
                    break
                raise TestFailure("response byte was 0x{:02x}, not 0x01".format(val))
            timeout_counter = timeout_counter + 1
            if timeout_counter > 20:
                raise TestFailure("timed out waiting for response")

        # Value
        val = 0
        for shift in [24, 16, 8, 0]:
            addon = yield self.host_spi_read_byte()
            val = val | (addon << shift)

        self.dut.spi_cs_n = 1
        yield self.host_finish()
        raise ReturnValue(val)

@cocotb.test()
def test_wishbone_write(dut):
    harness = SpiboneTest(dut, inspect.currentframe().f_code.co_name)
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
def test_spibone_write(dut, test_name, canary):
    addr = 0x40000004
    harness = SpiboneTest(dut, test_name)
    yield harness.reset()
    yield harness.host_spi_write(addr, canary)
    check_canary = yield harness.read(addr)
    if check_canary != canary:
        raise TestFailure("check_canary 0x{:08x} doesn't match written value 0x{:08x}".format(check_canary, canary))

@cocotb.coroutine
def test_spibone_read(dut, test_name, canary):
    addr = 0x40000004
    harness = SpiboneTest(dut, test_name)
    yield harness.reset()

    yield harness.write(addr, canary)
    check_canary = yield harness.host_spi_read(addr)
    if check_canary != canary:
        raise TestFailure("check_canary 0x{:08x} doesn't match written value 0x{:08x}".format(check_canary, canary))

@cocotb.test()
def test_spibone_read_aaaaaaaa(dut):
    yield test_spibone_read(dut, inspect.currentframe().f_code.co_name, 0xaaaaaaaa)

@cocotb.test()
def test_spibone_read_55555555(dut):
    yield test_spibone_read(dut, inspect.currentframe().f_code.co_name, 0x55555555)

@cocotb.test()
def test_spibone_write_aaaaaaaa(dut):
    yield test_spibone_write(dut, inspect.currentframe().f_code.co_name, 0xaaaaaaaa)

@cocotb.test()
def test_spibone_write_55555555(dut):
    yield test_spibone_write(dut, inspect.currentframe().f_code.co_name, 0x55555555)
