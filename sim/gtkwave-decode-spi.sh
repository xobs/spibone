#!/bin/bash
export PYTHONHASHSEED=1
exec `dirname $0`/gtkwave-sigrok-filter.py -P spi:cs=spi_cs_n:mosi=spi_mosi:miso=spi_miso:clk=spi_clk
