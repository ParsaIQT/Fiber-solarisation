#!/usr/bin/env python3
"""Render board layers to PNG for review:  python3 render.py OUT.png LAYERS [px_per_mm]
LAYERS is a comma separated KiCad layer list, e.g. F.Cu,F.Fab,Edge.Cuts"""
import os, sys, subprocess, tempfile
import cairosvg
HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, "..", "hardware", "ld405-driver.kicad_pcb"))


def render(out, layers, scale=10.0, pcb=PCB, mirror=False):
    with tempfile.TemporaryDirectory() as td:
        svg = os.path.join(td, "b.svg")
        cmd = ["kicad-cli", "pcb", "export", "svg", "--mode-single", "-o", svg, "-l", layers,
               "--page-size-mode", "2", "--exclude-drawing-sheet", "--drill-shape-opt", "2"]
        if mirror:
            cmd.append("--mirror")
        subprocess.run(cmd + [pcb], check=True, capture_output=True)
        # board is 160 mm wide; scale given in px/mm
        cairosvg.svg2png(url=svg, write_to=out, output_width=int(160 * scale + 40),
                         background_color="white")
    return out


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 10.0)
