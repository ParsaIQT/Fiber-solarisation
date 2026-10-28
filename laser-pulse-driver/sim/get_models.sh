#!/bin/sh
# Download the vendor SPICE models used by the testbench into sim/models/.
# (They are not redistributed in this repository.)
set -e
cd "$(dirname "$0")"
mkdir -p models && cd models
tmp=$(mktemp -d)
fetch() { curl -fsSL -A "Mozilla/5.0" -o "$tmp/$1" "$2"; }
# OPA2192 (TI SBOM860), INA180A1 (TI SBOMBC4)
fetch opa.zip https://www.ti.com/lit/zip/sbom860
fetch ina.zip https://www.ti.com/lit/zip/sbombc4
unzip -o -j -q "$tmp/opa.zip" "*OPAx192.LIB" -d .
unzip -o -j -q "$tmp/ina.zip" "*ina180a1.lib" -d .
# IRFR9024N (Infineon / International Rectifier)
fetch irfr9024n.spi https://www.infineon.com/assets/row/public/documents/24/50/irfr9024n.spi
cp "$tmp/irfr9024n.spi" irfr9024n.lib
rm -rf "$tmp"
ls -l
