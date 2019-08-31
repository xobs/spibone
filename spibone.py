from migen import *
from migen.fhdl.specials import Tristate, TSTriple
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
    def __init__(self, pads, three_wire=False, with_tristate=True):
        self.wishbone = wishbone.Interface()

        # # #

        clk = Signal()
        cs_n = Signal()
        mosi = Signal()
        miso = Signal()
        miso_en = Signal()

        counter = Signal(8)
        write_offset = Signal(5)
        command = Signal(8)
        address = Signal(32)
        value   = Signal(32)
        wr      = Signal()

        self.specials += [
            MultiReg(pads.clk, clk),
            MultiReg(pads.cs_n, cs_n),
        ]
        if three_wire:
            io = TSTriple()
            self.specials += io.get_tristate(pads.mosi)
            self.specials += MultiReg(io.i, mosi)
            self.comb += io.o.eq(miso)
            self.comb += io.oe.eq(miso_en)
        else:
            self.specials += MultiReg(pads.mosi, mosi)
            if with_tristate:
                self.specials += Tristate(pads.miso, miso, ~cs_n)
            else:
                self.comb += pads.miso.eq(miso)

        clk_last = Signal()
        clk_rising = Signal()
        clk_falling = Signal()
        self.sync += clk_last.eq(clk)
        self.comb += clk_rising.eq(clk & ~clk_last)
        self.comb += clk_falling.eq(~clk & clk_last)

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

        # Constantly have the counter increase, except when it's reset
        # in the IDLE state
        self.sync += If(cs_n, counter.eq(0)).Elif(clk_rising, counter.eq(counter + 1))

        fsm.act("IDLE",
            miso_en.eq(0),
            NextValue(miso, 1),
            If(clk_rising,
                NextState("GET_TYPE_BYTE"),
                NextValue(command, mosi),
            ),
        )

        # Determine if it's a read or a write
        fsm.act("GET_TYPE_BYTE",
            miso_en.eq(0),
            NextValue(miso, 1),
            If(counter == 8,
                # Write value
                If(command == 0,
                    NextValue(wr, 1),
                    NextState("READ_ADDRESS"),

                # Read value
                ).Elif(command == 1,
                    NextValue(wr, 0),
                    NextState("READ_ADDRESS"),
                ).Else(
                    NextState("END"),
                ),
            ),
            If(clk_rising,
                NextValue(command, Cat(mosi, command)),
            ),
        )

        fsm.act("READ_ADDRESS",
            miso_en.eq(0),
            If(counter == 32 + 8,
                If(wr,
                    NextState("READ_VALUE"),
                ).Else(
                    NextState("READ_WISHBONE"),
                )
            ),
            If(clk_rising,
                NextValue(address, Cat(mosi, address)),
            ),
        )

        fsm.act("READ_VALUE",
            miso_en.eq(0),
            If(counter == 32 + 32 + 8,
                NextState("WRITE_WISHBONE"),
            ),
            If(clk_rising,
                NextValue(value, Cat(mosi, value)),
            ),
        )

        fsm.act("WRITE_WISHBONE",
            self.wishbone.stb.eq(1),
            self.wishbone.we.eq(1),
            self.wishbone.cyc.eq(1),
            miso_en.eq(1),
            If(self.wishbone.ack | self.wishbone.err,
                NextState("WAIT_BYTE_BOUNDARY"),
            ),
        )

        fsm.act("READ_WISHBONE",
            self.wishbone.stb.eq(1),
            self.wishbone.we.eq(0),
            self.wishbone.cyc.eq(1),
            miso_en.eq(1),
            If(self.wishbone.ack | self.wishbone.err,
                NextState("WAIT_BYTE_BOUNDARY"),
                NextValue(value, self.wishbone.dat_r),
            ),
        )

        fsm.act("WAIT_BYTE_BOUNDARY",
            miso_en.eq(1),
            If(clk_falling,
                If(counter[0:3] == 0,
                    NextValue(miso, 0),
                    If(wr,
                        NextState("END"),
                    ).Else(
                        NextState("WRITE_RESPONSE"),
                    ),
                ),
            ),
        )

        # Write the "01" byte that indicates a response
        fsm.act("WRITE_RESPONSE",
            miso_en.eq(1),
            If(clk_falling,
                If(counter[0:3] == 0b111,
                    NextValue(miso, 1),
                ).Elif(counter[0:3] == 0,
                    NextValue(write_offset, 31),
                    NextState("WRITE_VALUE")
                ),
            ),
        )

        # Write the actual value
        fsm.act("WRITE_VALUE",
            miso_en.eq(1),
            NextValue(miso, value >> write_offset),
            If(clk_falling,
                NextValue(write_offset, write_offset - 1),
                If(write_offset == 0,
                    NextValue(miso, 0),
                    NextState("END"),
                ),
            ),
        )

        fsm.act("END",
            miso_en.eq(1),
        )