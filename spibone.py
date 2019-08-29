from migen import *
from migen.fhdl.specials import Tristate
from migen.genlib.cdc import MultiReg

from litex.soc.interconnect import csr_bus


class SPIControl(Module):
    """SPI Control (CPOL0 / CPHA0)
    proto:   | 16 bits command | n x 8 bits r/w |
    command: | 15: 1:write/0: read |  13-0: adr |
    """
    def __init__(self, pads, base=0x000, end=0x0ff, with_tristate=True):
        self.csr = csr = csr_bus.Interface()

        # # #

        clk = Signal()
        cs_n = Signal()
        mosi = Signal()
        miso = Signal()
        we = Signal()
        counter = Signal(8)
        senable = Signal()

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

        fsm.act("IDLE",
            If(clk_rising,
                NextValue(we, mosi),
                NextValue(counter, 1),
                NextState("ADR")
            ),
            senable.eq(1)
         )
        fsm.act("ADR",
            If(counter == 16,
                NextValue(counter, 0),
                If((csr.adr >= base) & (csr.adr <= end),
                    If(we,
                        NextState("WRITE")
                    ).Else(
                        NextState("READ")
                    )
                ).Else(
                    NextState("END")
                )
            ).Elif(clk_rising,
                NextValue(counter, counter + 1),
                NextValue(csr.adr, Cat(mosi, csr.adr))
            ),
            senable.eq(1)
         )
        fsm.act("WRITE",
            If(counter == 8,
                self.csr.we.eq(1),
                NextValue(counter, 0),
                If(csr.adr == end,
                    NextState("END")
                ).Else(
                    NextValue(csr.adr, csr.adr + 1)
                )
            ).Elif(clk_rising,
                NextValue(counter, counter + 1),
                NextValue(csr.dat_w, Cat(mosi, csr.dat_w))
            )
        )
        dat_r = Signal(8)
        fsm.act("READ",
            If(counter == 8,
                NextValue(counter, 0),
                If(csr.adr == end,
                    NextState("END")
                ).Else(
                    NextValue(csr.adr, csr.adr + 1)
                )
            ).Elif(clk_rising,
                NextValue(dat_r, Cat(Signal(), dat_r)),
                NextValue(counter, counter + 1)
            ).Elif(counter == 0,
                NextValue(dat_r, csr.dat_r)
            )
        )
        self.comb += miso.eq(dat_r[7])
        fsm.act("END")