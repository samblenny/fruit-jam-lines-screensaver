# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
from board import CKP, CKN, D0P, D0N, D1P, D1N, D2P, D2N
import bitmaptools
import displayio
from displayio import Bitmap, Group, Palette, TileGrid
import framebufferio
import gc
import math
import picodvi
import random
import supervisor
import sys
from time import sleep
from ulab import numpy as np


class LineTrail:
    """
    Data structure to hold a trail of lines.
    Each line has two endpoints. Each endpoint is defined by three values: x
    coordinate, y coordinate, and heading angle. The points drift at a fixed
    speed in the direction of their heading angles. The angles change when they
    bounce off an edge of the bitmap.
    """
    def __init__(self, x1, y1, angle1, x2, y2, angle2, bitmap, palette):
        first_color = 1
        first_line = (x1, y1, x2, y2, first_color)
        self.lines = [first_line]
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.angle1 = angle1
        self.angle2 = angle2
        self.color = first_color
        self.width = bitmap.width
        self.height = bitmap.height
        self.max_color = len(palette) - 1
        self.speed = 8
        self.max_lines = 21
        self.bg_color = 0

    def update_trail(self):
        """Compute endpoints of the next line and remove the last line"""
        spd = self.speed
        w = self.width
        h = self.height
        # Apply some random drift to the heading angles so that they don't get
        # stuck in a boring repetitive pattern
        drift = 2
        a1 = self.angle1 + random.uniform(-drift, drift) % 360
        a2 = self.angle2 + random.uniform(-drift, drift) % 360
        # Compute new start point
        a1r = math.radians(a1)
        x1 = self.x1 + (spd * math.cos(a1r))
        y1 = self.y1 + (spd * math.sin(a1r))
        # Adjust for bounce if new point crossed an edge
        if x1 < 0:
            x1 = 0 - x1
            a1 = (180 - a1) if (a1 <= 180) else (360 - (a1 - 180))
        if x1 >= width:
            x1 = width - (x1 - width)
            a1 = (180 - a1) if (a1 >= 0) else (180 + (360 - a1))
        if y1 < 0:
            y1 = 0 - y1
            a1 = (360 - a1) if (a1 <= 90) else (360 - a1)
        if y1 >= height:
            y1 = height - (y1 - height)
            a1 = 360 - a1
        self.x1 = x1
        self.y1 = y1
        self.angle1 = a1
        # Compute new end point
        a2r = math.radians(a2)
        x2 = self.x2 + (spd * math.cos(a2r))
        y2 = self.y2 + (spd * math.sin(a2r))
        # Adjust for bounce if new point crossed an edge
        if x2 < 0:
            x2 = 0 - x2
            a2 = (180 - a1) if (a1 <= 180) else (360 - (a1 - 180))
        if x2 >= width:
            x2 = width - (x2 - width)
            a2 = (180 - a2) if (a2 >= 0) else (180 + (360 - a2))
        if y2 < 0:
            y2 = 0 - y2
            a2 = (360 - a2) if (a2 <= 90) else (360 - a2)
        if y2 >= height:
            y2 = height - (y2 - height)
            a2 = 360 - a2
        self.x2 = x2
        self.y2 = y2
        self.angle2 = a2
        # Compute new color
        c = self.color
        c = (1) if (c == self.max_color) else (c + 1)
        self.color = c
        # Add new line to the list, deleting the oldest line if needed
        self.lines.append((round(x1), round(y1), round(x2), round(y2), c))
        if len(self.lines) > self.max_lines:
            self.lines.pop(0)


    def draw_into(self, bitmap):
        """Draw all the lines into the provided bitmap"""
        bitmap.fill(self.bg_color)
        for (x1, y1, x2, y2, color) in self.lines:
            bitmaptools.draw_line(bitmap, x1, y1, x2, y2, color)


def LCh_to_sRGB(L, C, h):
    """Convert L*C*h color to sRGB color using D65 whitepoint.
    L*: perceptual Lightness in range 0-1.0
    C*: Chroma in range 0-1.0
    h: hue angle in range 0-360 degrees
    Returns:
    (R, G, B): tuple of red, green, and blue values in range 0-255
    """
    # 1. Convert L*C*h to Lab (L stays the same)
    rh = math.radians(h)
    a = C * math.cos(rh)
    b = C * math.sin(rh)
    # 2. Convert L*a*b* (non-linear perceptual) to XYZ (linear)
    #    D65 reference white value: {X: 0.95047, Y: 1.0, Z: 1.08883}.
    epsilon = 0.008856
    k = 903.3
    fy = (L + 16) / 116
    fx = (a / 500) + fy
    fz = fy - (b / 200)
    xr = fx ** 3
    if xr <= epsilon:
        xr = ((116 * fx) - 16) / k
    yr = ((L + 16) / 116) ** 3
    if L <= k * epsilon:
        yr = L / k
    zr = fz ** 3
    if zr <= epsilon:
        zr = ((116 * fz) - 16) / k
    XYZ = np.array([[xr * 0.95047], [yr * 1.00], [zr * 1.08883]])  # D65
    # 3. Convert XYZ to linear sRGB.
    #    M is the chromatic adaptation matrix for XYZ to sRGB with D65 white
    M = np.array([
        [ 3.2404542, -1.5371385, -0.4985314],
        [-0.9692660,  1.8760108,  0.0415560],
        [ 0.0556434, -0.2040259,  1.0572252]])
    RGB_linear = np.dot(M, XYZ)
    # 4. Apply sRGB gamma curve compensation
    compand = np.vectorize(lambda v:
        (12.92 * v) if (v <= 0.0031308) else (pow(1.055 * v, 1/2.4) - 0.055))
    RGB = compand(RGB_linear)
    # 5. Scale output range from 0-1.0 up to 0-255
    scale = np.vectorize(lambda v: min(255, max(0, v * 25500)))
    sRGB = tuple([int(n) for n in np.flip(scale(RGB))])
    return sRGB

def fill_gradient_palette(palette, L, C):
    """Make gradient palette with variable hue at fixed Lightness & Chroma"""
    palette[0] = (0, 0, 0)
    n = len(palette)
    for i in range(1, n):
        h = 360 * (i / (n-1))
        sRGB = LCh_to_sRGB(L, C, h)
        palette[i] = sRGB

def init_display(width, height, color_depth):
    """Initialize the picodvi display
    Video mode compatibility:
    | Video Mode     | Fruit Jam | Metro RP2350 No PSRAM    |
    | -------------- | --------- | ------------------------ |
    | (320, 240,  8) | Yes!      | Yes!                     |
    | (320, 240, 16) | Yes!      | Yes!                     |
    | (320, 240, 32) | Yes!      | MemoryError exception :( |
    | (640, 480,  8) | Yes!      | MemoryError exception :( |
    """
    displayio.release_displays()
    gc.collect()
    fb = picodvi.Framebuffer(width, height, clk_dp=CKP, clk_dn=CKN,
        red_dp=D0P, red_dn=D0N, green_dp=D1P, green_dn=D1N,
        blue_dp=D2P, blue_dn=D2N, color_depth=color_depth)
    display = framebufferio.FramebufferDisplay(fb)
    supervisor.runtime.display = display
    return display


# Configure display with requested picodvi video mode
(width, height, color_depth) = (320, 240, 16)
display = init_display(width, height, color_depth)
display.auto_refresh = False

# Make a drawing canvas: bitmap + palette + tilegrid + group
palette = Palette(256)
bitmap = Bitmap(width, height, 256)
tilegrid = TileGrid(bitmap, pixel_shader=palette)
grp = Group(scale=1)
grp.append(tilegrid)
display.root_group = grp

# Make a color swirl palette
(L, C) = (0.24, 0.76)
fill_gradient_palette(palette, L, C)

# Initialize the trail of lines
lines = LineTrail(x1=31, y1=17, angle1=23, x2=163, y2=109, angle2=71,
    bitmap=bitmap, palette=palette)

# Main Loop
while True:
    lines.update_trail()
    lines.draw_into(bitmap)
    display.refresh()
    sleep(0.06)
