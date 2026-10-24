# OpenBurn

Open-source Laser CAM & Control software with zero external dependencies.

OpenBurn provides a high-performance vector/raster path compiler, G-code generator for GRBL-based laser cutters/engravers, and an interactive modern web/desktop interface.

## Features

- **Zero Third-Party Dependencies:** Built entirely with Python 3.10+ standard library (`math`, `struct`, `zlib`, `xml.etree`, `json`, `http.server`).
- **Comprehensive Project Support:**
  - Full support for `.lbrn` (XML) and `.lbrn2` (JSON) project formats.
  - SVG 1.1 / 2.0 import (transforms, viewBox, nested groups, path primitives).
- **Advanced Laser CAM Pipeline:**
  - **Vector Cutting (Line):** Accurate affine transformations, kerf compensation, smooth arc detection or chordal approximation.
  - **Raster Scanning (Fill):** Bi-directional scanning, arbitrary angles, overscan acceleration/deceleration buffers, multi-contour hole masking.
  - **Image Engraving:** Floyd-Steinberg, Atkinson, Jarvis, Stucki, Ordered, Threshold, Grayscale power mapping with fast pure-Python PNG chunk decoding.
  - **Layer Ordering & Z-Axis:** Up to 32 layers (`C00`–`C29`, `T1`, `T2`), priority sorting, inner-first path sequencing, automatic Z-step and multi-pass cutting.
- **Interactive Single-Page UI (Canvas 2D):**
  - Dark-themed responsive CAD canvas with pan/zoom.
  - Live jog controls, origin matrix (9 points), laser fire, home, and zeroing.
  - G-code preview and direct export.
  - Real-time hardware telemetry and status over Server-Sent Events (SSE).
- **Headless REST API:** Control the machine and compile projects headlessly or integrate into automation pipelines.

## Quick Start

### 1. Launch Interactive GUI
```bash
python3 -m openburn gui
```
Opens the browser interface at `http://127.0.0.1:8080`.

### 2. Run Headless Server
```bash
python3 -m openburn serve --port 8080 --bind 0.0.0.0
```

### 3. CLI G-Code Compiler
```bash
python3 -m openburn compile project.lbrn2 -o output.gcode
```

## Running Tests

All test vectors (geometry, raster, overscan, REST API) can be verified via:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

## Architecture

- `openburn/geometry.py`: Affine transformations, 2D primitives (Rect, Ellipse, Path, Bezier curves).
- `openburn/fill.py`: Scanline rasterization, overscan calculation, angle rotations.
- `openburn/raster.py`: PNG decoder and dithering kernels.
- `openburn/gcode.py`: GRBL G-code dialect generator, modal state tracking, motion planning.
- `openburn/project.py`: `.lbrn` and `.lbrn2` parsers and serializers.
- `openburn/api.py`: HTTP/SSE REST server and static web app server.
- `openburn/web/`: Modern zero-dependency HTML5 Canvas SPA.

## License

MIT License
