from migen import *
from migen.fhdl.specials import Tristate
from migen.genlib.cdc import MultiReg

from litex.soc.interconnect import wishbone, stream


class SpiWishboneBridge(Module):
    """SPI Control (CPOL0 / CPHA0)
    Read protocol:
        Write: 01 | AA | AA | AA | AA
        Read:  01 | VV | VV | VV | VV
    Write protocol:
        Write: 00 | AA | AA | AA | AA | VV | VV | VV | VV
        Read:  00
    "AA" is address, "VV" is value.  All bytes are big-endian.
    During the "Read" phase, the host constantly outputs "FF"
    until it has a response, at which point it outputs "00" (write)
    or "01" (read).
    """
    def __init__(self, pads, with_tristate=True):
        self.wishbone = wishbone.Interface()

        # # #

        clk = Signal()
        cs_n = Signal()
        mosi = Signal()
        miso = Signal()

        counter = Signal(8)
        current_byte = Signal(8)
        address = Signal(32)
        value = Signal(32)
        wr = Signal()

        self.specials += [
            MultiReg(pads.clk, clk),
            MultiReg(pads.cs_n, cs_n),
            MultiReg(pads.mosi, mosi)
        ]
        if with_tristate:
            self.specials += Tristate(pads.miso, miso, ~cs_n)
        else:
            self.comb += pads.miso.eq(miso)

        clk_last = Signal()
        clk_rising = Signal()
        self.sync += clk_last.eq(clk)
        self.comb += clk_rising.eq(clk & ~clk_last)

        fsm = FSM(reset_state="IDLE")
        fsm = ResetInserter()(fsm)
        self.submodules += fsm
        self.comb += fsm.reset.eq(cs_n)

        # Connect the Wishbone bus up to our values
        self.comb += [
            self.wishbone.adr.eq(address[2:]),
            self.wishbone.dat_w.eq(value),
            self.wishbone.sel.eq(2**len(self.wishbone.sel) - 1)
        ]

        fsm.act("IDLE",
            If(clk_rising,
                NextValue(counter, 0),
                NextState("RDWR")
            ),
        )

        # Determine if it's a read or a write
        fsm.act("RDWR",
            If(counter == 8,
                NextValue(counter, 0),
                # Write value
                If(current_byte == 0,
                    NextValue(wr, 1),
                    NextState("READ_ADDRESS"),
                # Read value
                ).Elif(current_byte == 1,
                    NextValue(wr, 1),
                    NextState("READ_ADDRESS"),
                ).Else(
                    NextState("END"),
                ),
            ).Elif(clk_rising,
                NextValue(current_byte, Cat(mosi, current_byte)),
                NextValue(counter, counter + 1),
            ),
        )

        fsm.act("READ_ADDRESS",
            If(counter == 32,
                NextValue(counter, 0),
                NextValue(miso, 1),
                If(wr,
                    NextState("READ_VALUE")
                ).Else(
                    NextState("READ_WISHBONE")
                )
            ).Elif(clk_rising,
                NextValue(counter, counter + 1),
                NextValue(address, Cat(mosi, address))
            ),
        )

        fsm.act("READ_VALUE",
            If(counter == 32,
                NextValue(counter, 0),
                NextState("WRITE_WISHBONE")
            ).Elif(clk_rising,
                NextValue(counter, counter + 1),
                NextValue(value, Cat(mosi, value))
            ),
        )

        fsm.act("WRITE_WISHBONE",
            self.wishbone.stb.eq(1),
            self.wishbone.we.eq(1),
            self.wishbone.cyc.eq(1),
            If(self.wishbone.ack | self.wishbone.err,
                NextState("END"),
                NextValue(miso, 0),
            ),
        )

        fsm.act("READ_WISHBONE",
            self.wishbone.stb.eq(1),
            self.wishbone.we.eq(0),
            self.wishbone.cyc.eq(1),
            If(self.wishbone.ack | self.wishbone.err,
                NextState("WAIT_BYTE_BOUNDARY")
            ),
            If(clk_rising,
                NextValue(counter, counter + 1),
            ),
        )

        fsm.act("WAIT_BYTE_BOUNDARY",
            If(counter[0:2] == 0,
                NextState("WRITE_RESPONSE"),
                NextValue(miso, 0),
                NextValue(counter, 0),
            ),
            If(clk_rising,
                NextValue(counter, counter + 1),
            ),
        )

        fsm.act("WRITE_RESPONSE",
            If(counter == 7,
                NextValue(miso, 1),
                NextValue(counter, 0),
                NextState("WRITE_VALUE")
            ),
            If(clk_rising,
                NextValue(counter, counter + 1),
            ),
        )

        fsm.act("WRITE_VALUE",
            NextValue(miso, value >> counter),
            If(counter == 32,
                NextState("END"),
            ),
            If(clk_rising,
                NextValue(counter, counter + 1),
            ),
        )
        fsm.act("END")