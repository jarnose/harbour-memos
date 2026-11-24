#!/usr/bin/env python3
"""Render icons/src/harbour-memos.svg into the four launcher icon sizes.

Needs cairosvg (pip install cairosvg). Run from anywhere:  python3 tools/make_icon.py
"""
import os
import cairosvg

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'icons')
svg = os.path.join(root, 'src', 'harbour-memos.svg')
for size in (86, 108, 128, 172):
    out_dir = os.path.join(root, f'{size}x{size}')
    os.makedirs(out_dir, exist_ok=True)
    cairosvg.svg2png(url=svg, write_to=os.path.join(out_dir, 'harbour-memos.png'),
                     output_width=size, output_height=size)
    print('wrote', size)
