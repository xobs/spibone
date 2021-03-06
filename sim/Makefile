###############################################################################
# Copyright (c) 2013, 2018 Potential Ventures Ltd
# Copyright (c) 2013 SolarFlare Communications Inc
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of Potential Ventures Ltd,
#       SolarFlare Communications Inc nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL POTENTIAL VENTURES LTD BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
###############################################################################

# Default to verilog
TOPLEVEL_LANG ?= verilog

WPWD=$(shell sh -c 'pwd -W')
PWD=$(shell pwd)

ifeq ($(OS),Msys)
WPWD=$(shell sh -c 'pwd -W')
PYTHONPATH := $(PWD)/..;$(PYTHONPATH)
else
WPWD=$(shell pwd)
PYTHONPATH := $(PWD)/..:$(PYTHONPATH)
endif

ifeq ($(WIRES),2)
VERILOG_SOURCES = $(WPWD)/dut-twowire.v $(WPWD)/tb.v
CUSTOM_COMPILE_DEPS = $(PWD)/dut-twowire.v
else
ifeq ($(WIRES),3)
VERILOG_SOURCES = $(WPWD)/dut-threewire.v $(WPWD)/tb.v
CUSTOM_COMPILE_DEPS = $(PWD)/dut-threewire.v
else
VERILOG_SOURCES = $(WPWD)/dut-fourwire.v $(WPWD)/tb.v
CUSTOM_COMPILE_DEPS = $(PWD)/dut-fourwire.v
endif
endif
TOPLEVEL = tb
MODULE = test-spibone


include $(shell cocotb-config --makefiles)/Makefile.inc
include $(shell cocotb-config --makefiles)/Makefile.sim

$(PWD)/dut-fourwire.v: generate-verilog.py ../spibone.py
	cd ..
	PYTHONPATH=../deps/litex:../deps/migen:../deps/litedram:.. python3 generate-verilog.py --wires 4
	mv build/gateware/dut.v dut-fourwire.v
	mv build/gateware/mem.init .

$(PWD)/dut-threewire.v: generate-verilog.py ../spibone.py
	cd $(PWD)
	PYTHONPATH=../deps/litex:../deps/migen:../deps/litedram:.. python3 generate-verilog.py --wires 3
	mv build/gateware/dut.v dut-threewire.v

$(PWD)/dut-twowire.v: generate-verilog.py ../spibone.py
	cd $(PWD)
	PYTHONPATH=../deps/litex:../deps/migen:../deps/litedram:.. python3 generate-verilog.py --wires 2
	mv build/gateware/dut.v dut-twowire.v