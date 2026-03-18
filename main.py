import math
import io
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple

import streamlit as st

st.set_page_config(page_title="Laser Test Matrix Generator", page_icon="🧪", layout="wide")

# ============================================================
# Models
# ============================================================

@dataclass
class MatrixConfig:
    title: str
    x: float
    y: float
    width: float
    height: float
    rows: int
    cols: int
    row_label: str
    col_label: str
    row_start: float
    row_stop: float
    row_step: float
    col_start: float
    col_stop: float
    col_step: float
    unit_row: str
    unit_col: str
    hatch_spacing: float
    passes: int
    angle_deg: float
    draw_border: bool
    mark_text: bool


# ============================================================
# Helpers
# ============================================================

def fmt_num(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def frange_from_inputs(start: float, stop: float, step: float) -> List[float]:
    vals = []
    if step == 0:
        return [start]
    if stop >= start:
        v = start
        while v <= stop + 1e-9:
            vals.append(round(v, 6))
            v += step
    else:
        v = start
        while v >= stop - 1e-9:
            vals.append(round(v, 6))
            v -= abs(step)
    return vals


def build_axis_values(start: float, stop: float, step: float, fallback_count: int) -> List[float]:
    vals = frange_from_inputs(start, stop, step)
    if len(vals) == 0:
        return [start]
    if fallback_count > 0 and len(vals) != fallback_count:
        return vals
    return vals


def mm(v: float) -> str:
    return f"{v:.3f}mm"


def svg_rect(x: float, y: float, w: float, h: float, stroke: str = "black", fill: str = "none", stroke_width: float = 0.15) -> str:
    return f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" stroke="{stroke}" fill="{fill}" stroke-width="{stroke_width:.3f}" />'


def svg_line(x1: float, y1: float, x2: float, y2: float, stroke: str = "black", stroke_width: float = 0.12) -> str:
    return f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="{stroke}" stroke-width="{stroke_width:.3f}" />'


def svg_text(x: float, y: float, text: str, size: float = 3.0, anchor: str = "middle", rotate: float = 0.0) -> str:
    transform = f' transform="rotate({rotate:.3f} {x:.3f} {y:.3f})"' if abs(rotate) > 1e-9 else ""
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size:.3f}" text-anchor="{anchor}" font-family="Arial"{transform}>{safe}</text>'


def hatch_lines_for_rect(x: float, y: float, w: float, h: float, spacing: float, angle_deg: float, passes: int) -> List[Tuple[float, float, float, float]]:
    # Simplified hatch generator: 0 deg = horizontal, 90 deg = vertical, other angles use a general clipping approach.
    lines = []
    if spacing <= 0:
        return lines

    angle = math.radians(angle_deg % 180)
    dx = math.cos(angle)
    dy = math.sin(angle)
    nx = -dy
    ny = dx

    corners = [
        (x, y),
        (x + w, y),
        (x + w, y + h),
        (x, y + h),
    ]
    projections = [cx * nx + cy * ny for cx, cy in corners]
    pmin = min(projections)
    pmax = max(projections)

    def intersect_line_with_rect(c: float):
        pts = []
        # x = const boundaries
        if abs(dy) > 1e-9:
            for xx in (x, x + w):
                yy = (c - nx * xx) / ny if abs(ny) > 1e-9 else None
                if yy is not None and y - 1e-9 <= yy <= y + h + 1e-9:
                    pts.append((xx, yy))
        # y = const boundaries
        if abs(dx) > 1e-9:
            for yy in (y, y + h):
                xx = (c - ny * yy) / nx if abs(nx) > 1e-9 else None
                if xx is not None and x - 1e-9 <= xx <= x + w + 1e-9:
                    pts.append((xx, yy))
        # dedupe
        uniq = []
        for p in pts:
            if not any(abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6 for q in uniq):
                uniq.append(p)
        if len(uniq) >= 2:
            return uniq[0], uniq[1]
        return None

    count = max(1, passes)
    for pass_idx in range(count):
        offset = (pass_idx / count) * spacing
        c = pmin - spacing * 2 + offset
        while c <= pmax + spacing * 2:
            hit = intersect_line_with_rect(c)
            if hit:
                (x1, y1), (x2, y2) = hit
                lines.append((x1, y1, x2, y2))
            c += spacing
    return lines


def generate_matrix_svg(matrix: MatrixConfig) -> str:
    col_values = build_axis_values(matrix.col_start, matrix.col_stop, matrix.col_step, matrix.cols)
    row_values = build_axis_values(matrix.row_start, matrix.row_stop, matrix.row_step, matrix.rows)

    cols = len(col_values)
    rows = len(row_values)

    cell_w = matrix.width / cols
    cell_h = matrix.height / rows

    elements = []

    if matrix.draw_border:
        elements.append(svg_rect(matrix.x, matrix.y, matrix.width, matrix.height, stroke_width=0.25))

    # Title
    elements.append(svg_text(matrix.x + matrix.width / 2, matrix.y - 4, matrix.title, size=4.0))

    # Grid and hatch
    for r in range(rows):
        for c in range(cols):
            cx = matrix.x + c * cell_w
            cy = matrix.y + r * cell_h
            elements.append(svg_rect(cx, cy, cell_w, cell_h, stroke_width=0.12))
            for x1, y1, x2, y2 in hatch_lines_for_rect(cx + 0.6, cy + 0.6, cell_w - 1.2, cell_h - 1.2, matrix.hatch_spacing, matrix.angle_deg, matrix.passes):
                elements.append(svg_line(x1, y1, x2, y2, stroke_width=0.10))

            if matrix.mark_text:
                label = f"{matrix.col_label}={fmt_num(col_values[c])}{matrix.unit_col}\n{matrix.row_label}={fmt_num(row_values[r])}{matrix.unit_row}"
                elements.append(svg_text(cx + cell_w / 2, cy + cell_h / 2 - 1.0, f"{matrix.col_label}={fmt_num(col_values[c])}{matrix.unit_col}", size=2.2))
                elements.append(svg_text(cx + cell_w / 2, cy + cell_h / 2 + 2.0, f"{matrix.row_label}={fmt_num(row_values[r])}{matrix.unit_row}", size=2.2))

    # Column headers
    for c, val in enumerate(col_values):
        cx = matrix.x + c * cell_w + cell_w / 2
        elements.append(svg_text(cx, matrix.y - 1.3, fmt_num(val), size=2.6))

    # Row headers
    for r, val in enumerate(row_values):
        cy = matrix.y + r * cell_h + cell_h / 2 + 0.8
        elements.append(svg_text(matrix.x - 3.0, cy, fmt_num(val), size=2.6, rotate=-90))

    # Axis captions
    elements.append(svg_text(matrix.x + matrix.width / 2, matrix.y + matrix.height + 5.0, f"{matrix.col_label} [{matrix.unit_col}]", size=3.0))
    elements.append(svg_text(matrix.x - 9.0, matrix.y + matrix.height / 2, f"{matrix.row_label} [{matrix.unit_row}]", size=3.0, rotate=-90))

    return "\n".join(elements)


def generate_full_svg(matrices: List[MatrixConfig], page_w: float, page_h: float, part_name: str) -> str:
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_w:.3f}mm" height="{page_h:.3f}mm" viewBox="0 0 {page_w:.3f} {page_h:.3f}">',
        '<rect x="0" y="0" width="100%" height="100%" fill="white" />',
        svg_text(page_w / 2, 8, f"Laser Test Matrix - {part_name}", size=5.0),
        svg_text(page_w / 2, 13, "Black lines = vector layout only. Use labels to apply machine settings manually or via CAM workflow.", size=2.8),
    ]

    for m in matrices:
        body.append(generate_matrix_svg(m))

    body.append("</svg>")
    return "\n".join(body)


def default_matrix_presets() -> List[dict]:
    return [
        {
            "title": "Power vs Speed",
            "row_label": "Power",
            "col_label": "Speed",
            "row_start": 10.0,
            "row_stop": 100.0,
            "row_step": 10.0,
            "col_start": 100.0,
            "col_stop": 1000.0,
            "col_step": 100.0,
            "unit_row": "%",
            "unit_col": "mm/s",
        },
        {
            "title": "Power vs Frequency",
            "row_label": "Power",
            "col_label": "Freq",
            "row_start": 10.0,
            "row_stop": 100.0,
            "row_step": 10.0,
            "col_start": 1000.0,
            "col_stop": 20000.0,
            "col_step": 1000.0,
            "unit_row": "%",
            "unit_col": "Hz",
        },
        {
            "title": "Speed vs Frequency",
            "row_label": "Speed",
            "col_label": "Freq",
            "row_start": 100.0,
            "row_stop": 1000.0,
            "row_step": 100.0,
            "col_start": 1000.0,
            "col_stop": 20000.0,
            "col_step": 1000.0,
            "unit_row": "mm/s",
            "unit_col": "Hz",
        },
        {
            "title": "Hatch vs Power",
            "row_label": "Hatch",
            "col_label": "Power",
            "row_start": 0.03,
            "row_stop": 0.15,
            "row_step": 0.02,
            "col_start": 10.0,
            "col_stop": 100.0,
            "col_step": 10.0,
            "unit_row": "mm",
            "unit_col": "%",
        },
    ]


# ============================================================
# UI
# ============================================================

st.title("🧪 Laser Engraving Test Matrix Generator")
st.caption("Generate SVG laser test layouts for power, speed, frequency, hatch spacing, and other parameter combinations.")

with st.sidebar:
    st.header("Page / Part")
    part_name = st.text_input("Part / material name", value="Anodized Aluminum 100x100")
    page_w = st.number_input("Canvas width (mm)", min_value=50.0, max_value=1000.0, value=210.0, step=10.0)
    page_h = st.number_input("Canvas height (mm)", min_value=50.0, max_value=1000.0, value=297.0, step=10.0)
    st.divider()
    st.write("Use the page as a full sheet, then place one or more 100x100 mm test segments on it.")

if "matrices" not in st.session_state:
    presets = default_matrix_presets()
    st.session_state.matrices = [
        {
            "title": presets[0]["title"],
            "x": 15.0,
            "y": 25.0,
            "width": 100.0,
            "height": 100.0,
            "rows": 10,
            "cols": 10,
            "row_label": presets[0]["row_label"],
            "col_label": presets[0]["col_label"],
            "row_start": presets[0]["row_start"],
            "row_stop": presets[0]["row_stop"],
            "row_step": presets[0]["row_step"],
            "col_start": presets[0]["col_start"],
            "col_stop": presets[0]["col_stop"],
            "col_step": presets[0]["col_step"],
            "unit_row": presets[0]["unit_row"],
            "unit_col": presets[0]["unit_col"],
            "hatch_spacing": 1.0,
            "passes": 1,
            "angle_deg": 45.0,
            "draw_border": True,
            "mark_text": True,
        }
    ]

col_a, col_b, col_c = st.columns([1, 1, 2])
with col_a:
    if st.button("➕ Add empty matrix"):
        st.session_state.matrices.append(
            {
                "title": "Custom Matrix",
                "x": 15.0,
                "y": 140.0,
                "width": 100.0,
                "height": 100.0,
                "rows": 5,
                "cols": 5,
                "row_label": "Param Y",
                "col_label": "Param X",
                "row_start": 1.0,
                "row_stop": 5.0,
                "row_step": 1.0,
                "col_start": 1.0,
                "col_stop": 5.0,
                "col_step": 1.0,
                "unit_row": "",
                "unit_col": "",
                "hatch_spacing": 1.0,
                "passes": 1,
                "angle_deg": 45.0,
                "draw_border": True,
                "mark_text": True,
            }
        )
with col_b:
    preset_choice = st.selectbox(
        "Preset",
        [p["title"] for p in default_matrix_presets()],
        index=0,
        key="preset_choice"
    )
with col_c:
    if st.button("📦 Add preset matrix"):
        preset = next(p for p in default_matrix_presets() if p["title"] == preset_choice)
        st.session_state.matrices.append(
            {
                "title": preset["title"],
                "x": 15.0,
                "y": 25.0 + 115.0 * (len(st.session_state.matrices) % 2),
                "width": 100.0,
                "height": 100.0,
                "rows": len(frange_from_inputs(preset["row_start"], preset["row_stop"], preset["row_step"])),
                "cols": len(frange_from_inputs(preset["col_start"], preset["col_stop"], preset["col_step"])),
                "row_label": preset["row_label"],
                "col_label": preset["col_label"],
                "row_start": preset["row_start"],
                "row_stop": preset["row_stop"],
                "row_step": preset["row_step"],
                "col_start": preset["col_start"],
                "col_stop": preset["col_stop"],
                "col_step": preset["col_step"],
                "unit_row": preset["unit_row"],
                "unit_col": preset["unit_col"],
                "hatch_spacing": 1.0,
                "passes": 1,
                "angle_deg": 45.0,
                "draw_border": True,
                "mark_text": True,
            }
        )

st.divider()

matrices: List[MatrixConfig] = []
remove_index = None

for idx, matrix_data in enumerate(st.session_state.matrices):
    with st.expander(f"Matrix {idx + 1}: {matrix_data['title']}", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        matrix_data["title"] = c1.text_input("Title", value=matrix_data["title"], key=f"title_{idx}")
        matrix_data["x"] = c2.number_input("X (mm)", min_value=0.0, value=float(matrix_data["x"]), step=1.0, key=f"x_{idx}")
        matrix_data["y"] = c3.number_input("Y (mm)", min_value=0.0, value=float(matrix_data["y"]), step=1.0, key=f"y_{idx}")
        matrix_data["width"] = c4.number_input("Width (mm)", min_value=10.0, value=float(matrix_data["width"]), step=1.0, key=f"w_{idx}")
        matrix_data["height"] = st.number_input("Height (mm)", min_value=10.0, value=float(matrix_data["height"]), step=1.0, key=f"h_{idx}")

        r1, r2, r3, r4 = st.columns(4)
        matrix_data["row_label"] = r1.text_input("Row label", value=matrix_data["row_label"], key=f"rlabel_{idx}")
        matrix_data["row_start"] = r2.number_input("Row start", value=float(matrix_data["row_start"]), step=1.0, key=f"rstart_{idx}")
        matrix_data["row_stop"] = r3.number_input("Row stop", value=float(matrix_data["row_stop"]), step=1.0, key=f"rstop_{idx}")
        matrix_data["row_step"] = r4.number_input("Row step", value=float(matrix_data["row_step"]), step=0.01, key=f"rstep_{idx}")

        rr1, rr2 = st.columns(2)
        matrix_data["unit_row"] = rr1.text_input("Row unit", value=matrix_data["unit_row"], key=f"urow_{idx}")
        row_values = frange_from_inputs(float(matrix_data["row_start"]), float(matrix_data["row_stop"]), float(matrix_data["row_step"]))
        matrix_data["rows"] = rr2.number_input("Detected rows", min_value=1, value=max(1, len(row_values)), step=1, key=f"rows_{idx}")

        c1, c2, c3, c4 = st.columns(4)
        matrix_data["col_label"] = c1.text_input("Column label", value=matrix_data["col_label"], key=f"clabel_{idx}")
        matrix_data["col_start"] = c2.number_input("Column start", value=float(matrix_data["col_start"]), step=1.0, key=f"cstart_{idx}")
        matrix_data["col_stop"] = c3.number_input("Column stop", value=float(matrix_data["col_stop"]), step=1.0, key=f"cstop_{idx}")
        matrix_data["col_step"] = c4.number_input("Column step", value=float(matrix_data["col_step"]), step=0.01, key=f"cstep_{idx}")

        cc1, cc2 = st.columns(2)
        matrix_data["unit_col"] = cc1.text_input("Column unit", value=matrix_data["unit_col"], key=f"ucol_{idx}")
        col_values = frange_from_inputs(float(matrix_data["col_start"]), float(matrix_data["col_stop"]), float(matrix_data["col_step"]))
        matrix_data["cols"] = cc2.number_input("Detected columns", min_value=1, value=max(1, len(col_values)), step=1, key=f"cols_{idx}")

        p1, p2, p3, p4, p5 = st.columns(5)
        matrix_data["hatch_spacing"] = p1.number_input("Hatch spacing (mm)", min_value=0.05, value=float(matrix_data["hatch_spacing"]), step=0.05, key=f"hatch_{idx}")
        matrix_data["passes"] = p2.number_input("Passes", min_value=1, max_value=10, value=int(matrix_data["passes"]), step=1, key=f"passes_{idx}")
        matrix_data["angle_deg"] = p3.number_input("Angle (deg)", min_value=0.0, max_value=180.0, value=float(matrix_data["angle_deg"]), step=5.0, key=f"angle_{idx}")
        matrix_data["draw_border"] = p4.checkbox("Border", value=bool(matrix_data["draw_border"]), key=f"border_{idx}")
        matrix_data["mark_text"] = p5.checkbox("Cell text", value=bool(matrix_data["mark_text"]), key=f"txt_{idx}")

        if st.button(f"🗑 Remove matrix {idx + 1}", key=f"rm_{idx}"):
            remove_index = idx

    matrices.append(MatrixConfig(**matrix_data))

if remove_index is not None:
    st.session_state.matrices.pop(remove_index)
    st.rerun()

st.divider()

svg_content = generate_full_svg(matrices, page_w, page_h, part_name)

preview_col, export_col = st.columns([3, 2])
with preview_col:
    st.subheader("Preview")
    st.components.v1.html(svg_content, height=700, scrolling=True)

with export_col:
    st.subheader("Export")
    st.download_button(
        label="⬇ Download SVG",
        data=svg_content.encode("utf-8"),
        file_name="laser_test_matrix.svg",
        mime="image/svg+xml",
    )

    config_json = json.dumps([asdict(m) for m in matrices], indent=2)
    st.download_button(
        label="⬇ Download JSON config",
        data=config_json.encode("utf-8"),
        file_name="laser_test_matrix_config.json",
        mime="application/json",
    )

    st.code(config_json, language="json")

st.divider()
st.subheader("Recommended test types")
left, right = st.columns(2)
with left:
    st.markdown(
        """
- **Power vs Speed** → fastest way to find visible mark depth / darkness window.
- **Power vs Frequency** → useful for fiber laser surface quality and color behavior.
- **Speed vs Frequency** → useful after power is roughly fixed.
- **Power vs Hatch** → useful for fill uniformity and overlap.
        """
    )
with right:
    st.markdown(
        """
- **Passes vs Power** → for deep engraving.
- **Defocus vs Power** → for wide marks or controlled annealing.
- **Line interval vs Speed** → for filled areas.
- **Angle test** → 0°, 45°, 90° hatch direction comparison.
        """
    )

st.info(
    "DXF can store geometry, but it does not reliably carry laser-process settings between software packages. "
    "SVG is usually better for a labeled test layout like this. The machine settings are normally applied in the laser software per color, layer, or selected objects."
)

st.divider()
st.subheader("Parameter Theory")

t1, t2, t3, t4 = st.tabs(["Power", "Speed", "Frequency", "Starter presets"])

with t1:
    st.markdown(
        """
### Power
Power is the overall laser output level.

- **Higher power** = more energy into the material
- **Lower power** = lighter interaction, less depth, less burn risk

**What happens on the material:**
- deeper engraving
- darker mark on many materials
- easier material removal
- more melting or burning if too high

**Use more power when:**
- you want deeper engraving
- you want faster cutting
- the material is difficult to mark

**Use less power when:**
- you want fine detail
- edges burn too much
- the mark is too deep or too wide
        """
    )

with t2:
    st.markdown(
        """
### Speed
Speed is how fast the beam moves over the part.

- **Lower speed** = beam stays longer on one spot
- **Higher speed** = less dwell time, lighter mark

**What happens on the material:**
- slow speed gives more heat and deeper effect
- high speed gives lighter, cleaner results
- too slow can char, melt, or widen the mark

**Typical direction:**
- **engraving:** medium power + medium/high speed
- **deep engraving:** higher power + lower speed
- **cutting:** high power + lower speed until the beam fully penetrates
        """
    )

with t3:
    st.markdown(
        """
### Frequency
Frequency is the pulse rate of the laser, often set in **kHz**.

Think of it like this:
- **low frequency** = fewer but stronger hits
- **high frequency** = more frequent but softer hits

For a machine with **0–20 kHz**:

- **0–5 kHz** → stronger pulse impact, more aggressive removal
- **5–10 kHz** → balanced general-purpose range
- **10–20 kHz** → smoother heating, often cleaner visual finish

**What happens on the material:**
- lower frequency often helps with stronger ablation and deeper material removal
- higher frequency often gives smoother behavior and cleaner-looking finish
- the best value depends on laser type and material

**Good rule of thumb:**
- for **deep engraving / aggressive removal**: test lower-to-medium frequency
- for **surface marking / smoother finish**: test medium-to-high frequency
- for **cutting**: test both penetration and edge quality, because some materials like smoother high-frequency behavior while others prefer stronger lower-frequency pulses
        """
    )

with t4:
    st.markdown(
        """
### Recommended starter presets
These are **starting points only**. Always make a test matrix on the real material.

#### 1. Surface engraving / marking
- Power: **20–50%**
- Speed: **400–1200 mm/s**
- Frequency: **10–20 kHz**
- Hatch: **0.05–0.10 mm**
- Passes: **1**

Goal: visible mark, minimal heat damage, good detail.

#### 2. Deep engraving
- Power: **60–100%**
- Speed: **100–500 mm/s**
- Frequency: **2–10 kHz**
- Hatch: **0.03–0.08 mm**
- Passes: **2–10**

Goal: stronger material removal and depth.

#### 3. Cutting
- Power: **80–100%**
- Speed: **5–150 mm/s**
- Frequency: **5–20 kHz**
- Passes: depends on thickness

Goal: full penetration with acceptable edge quality.

### Recommended workflow
1. First test **Power vs Speed**
2. Find 2–3 promising zones
3. Then test **Frequency sweep** on those zones
4. Then fine-tune **hatch** and **passes**
        """
    )

st.divider()
st.subheader("Quick preset builder")

preset_cols = st.columns(3)
with preset_cols[0]:
    if st.button("Load engraving preset"):
        st.session_state.matrices = [
            {
                "title": "Engraving - Power vs Speed",
                "x": 15.0,
                "y": 25.0,
                "width": 100.0,
                "height": 100.0,
                "rows": 7,
                "cols": 9,
                "row_label": "Power",
                "col_label": "Speed",
                "row_start": 20.0,
                "row_stop": 50.0,
                "row_step": 5.0,
                "col_start": 400.0,
                "col_stop": 1200.0,
                "col_step": 100.0,
                "unit_row": "%",
                "unit_col": "mm/s",
                "hatch_spacing": 0.08,
                "passes": 1,
                "angle_deg": 45.0,
                "draw_border": True,
                "mark_text": True,
            },
            {
                "title": "Engraving - Frequency Sweep",
                "x": 125.0,
                "y": 25.0,
                "width": 70.0,
                "height": 100.0,
                "rows": 5,
                "cols": 5,
                "row_label": "Power",
                "col_label": "Freq",
                "row_start": 25.0,
                "row_stop": 45.0,
                "row_step": 5.0,
                "col_start": 2.0,
                "col_stop": 20.0,
                "col_step": 4.5,
                "unit_row": "%",
                "unit_col": "kHz",
                "hatch_spacing": 0.08,
                "passes": 1,
                "angle_deg": 45.0,
                "draw_border": True,
                "mark_text": True,
            }
        ]
        st.rerun()

with preset_cols[1]:
    if st.button("Load deep engraving preset"):
        st.session_state.matrices = [
            {
                "title": "Deep Engraving - Power vs Speed",
                "x": 15.0,
                "y": 25.0,
                "width": 100.0,
                "height": 100.0,
                "rows": 9,
                "cols": 9,
                "row_label": "Power",
                "col_label": "Speed",
                "row_start": 60.0,
                "row_stop": 100.0,
                "row_step": 5.0,
                "col_start": 100.0,
                "col_stop": 500.0,
                "col_step": 50.0,
                "unit_row": "%",
                "unit_col": "mm/s",
                "hatch_spacing": 0.05,
                "passes": 3,
                "angle_deg": 45.0,
                "draw_border": True,
                "mark_text": True,
            },
            {
                "title": "Deep Engraving - Frequency Sweep",
                "x": 125.0,
                "y": 25.0,
                "width": 70.0,
                "height": 100.0,
                "rows": 5,
                "cols": 5,
                "row_label": "Passes",
                "col_label": "Freq",
                "row_start": 2.0,
                "row_stop": 10.0,
                "row_step": 2.0,
                "col_start": 2.0,
                "col_stop": 10.0,
                "col_step": 2.0,
                "unit_row": "",
                "unit_col": "kHz",
                "hatch_spacing": 0.05,
                "passes": 1,
                "angle_deg": 45.0,
                "draw_border": True,
                "mark_text": True,
            }
        ]
        st.rerun()

with preset_cols[2]:
    if st.button("Load cutting preset"):
        st.session_state.matrices = [
            {
                "title": "Cutting - Power vs Speed",
                "x": 15.0,
                "y": 25.0,
                "width": 100.0,
                "height": 100.0,
                "rows": 5,
                "cols": 10,
                "row_label": "Power",
                "col_label": "Speed",
                "row_start": 80.0,
                "row_stop": 100.0,
                "row_step": 5.0,
                "col_start": 5.0,
                "col_stop": 140.0,
                "col_step": 15.0,
                "unit_row": "%",
                "unit_col": "mm/s",
                "hatch_spacing": 1.00,
                "passes": 1,
                "angle_deg": 0.0,
                "draw_border": True,
                "mark_text": True,
            },
            {
                "title": "Cutting - Frequency Sweep",
                "x": 125.0,
                "y": 25.0,
                "width": 70.0,
                "height": 100.0,
                "rows": 4,
                "cols": 4,
                "row_label": "Speed",
                "col_label": "Freq",
                "row_start": 20.0,
                "row_stop": 80.0,
                "row_step": 20.0,
                "col_start": 5.0,
                "col_stop": 20.0,
                "col_step": 5.0,
                "unit_row": "mm/s",
                "unit_col": "kHz",
                "hatch_spacing": 1.00,
                "passes": 1,
                "angle_deg": 0.0,
                "draw_border": True,
                "mark_text": True,
            }
        ]
        st.rerun()
