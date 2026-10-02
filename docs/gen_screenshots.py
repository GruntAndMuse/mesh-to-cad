#!/usr/bin/env python3
"""
Generate annotated terminal screenshots for the mesh-to-cad QUICKSTART.

WHAT THIS DOES:
    Reads captured real terminal output (text files) and renders them as
    terminal-style PNGs: dark background, monospace font, a `$` prompt line
    showing the command that was run, then the output. Red circles/arrows
    highlight the parts a beginner needs to notice.

WHY GENERATED AND NOT REAL SCREENSHOTS:
    Real terminal screenshots vary by OS, font, and window size — and can't
    be re-rendered when the CLI's output changes. These are generated from
    ACTUAL captured output (not mocked), so they stay truthful, and
    re-running this script after a CLI change refreshes them.

    The annotations use the universal "look here" language: red circles and
    arrows. No legend needed — everyone knows what a red circle means.

USAGE:
    python3 gen_screenshots.py
    Output: docs/screenshots/*.png
"""
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Layout constants. WHY THESE NUMBERS: 14pt DejaVu Sans Mono at 900px wide
# fits ~110 columns — enough for the CLI's longest lines without wrapping.
# Line height 22px gives breathing room without wasting vertical space.
# ---------------------------------------------------------------------------
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 15
LINE_H = 23
PAD = 24
IMG_W = 960
BG = (18, 18, 24)          # near-black with a blue tint (terminal-like)
FG = (220, 220, 220)       # off-white text
PROMPT_FG = (120, 220, 120)  # green prompt
RED = (255, 70, 70)        # annotation red
CAPTION_BG = (30, 30, 40)
CAPTION_FG = (180, 180, 200)

OUT_DIR = Path(__file__).resolve().parent / "screenshots"
CAPTURE_DIR = Path("/tmp/shot-capture")


def load_font(size=FONT_SIZE, bold=False):
    path = FONT_PATH.replace("SansMono.ttf",
                             "SansMono-Bold.ttf" if bold else "SansMono.ttf")
    return ImageFont.truetype(path, size)


def wrap_line(draw, font, text, max_w):
    """Wrap a long line to fit. WHY: real terminal output wraps; our image
    must too, or long lines get clipped and the screenshot lies."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def render(command: str, output_text: str, caption: str,
           highlights: list, out_name: str):
    """Render one annotated screenshot.

    highlights: list of dicts with:
        {"pattern": str, "label": str} — find first line containing pattern,
            draw a red ellipse around the matched region + label text.
        {"line": int, "label": str} — highlight a whole line by index.
    """
    font = load_font()
    bold = load_font(bold=True)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_w = IMG_W - 2 * PAD

    # Build the line list: prompt line + wrapped output.
    prompt = f"$ {command}"
    raw_lines = [prompt] + output_text.splitlines()
    lines = []
    is_prompt = []
    for i, rl in enumerate(raw_lines):
        if i == 0:
            lines.append(rl)
            is_prompt.append(True)
            continue
        # Preserve intentional blank lines (they're paragraph breaks).
        if not rl.strip():
            lines.append("")
            is_prompt.append(False)
            continue
        for wl in wrap_line(tmp, font, rl, max_w):
            lines.append(wl)
            is_prompt.append(False)

    # Cap height: if output is huge, show the head and tail with a gap marker.
    # WHY HEAD+TAIL: for the full-pipeline screenshot, the beginning (steps)
    # and the end (summary + next steps) are both the point. The middle is
    # detail. Showing only the head would hide the payoff.
    MAX_LINES = 38
    HEAD_LINES = 24
    TAIL_LINES = 12
    if len(lines) > MAX_LINES:
        head = lines[:HEAD_LINES]
        head_prompt = is_prompt[:HEAD_LINES]
        tail = lines[-TAIL_LINES:]
        tail_prompt = is_prompt[-TAIL_LINES:]
        gap = ["", "  [... middle of output ...]", ""]
        gap_prompt = [False, False, False]
        lines = head + gap + tail
        is_prompt = head_prompt + gap_prompt + tail_prompt

    caption_h = 44
    img_h = PAD * 2 + len(lines) * LINE_H + caption_h
    img = Image.new("RGB", (IMG_W, img_h), BG)
    d = ImageDraw.Draw(img)

    # Text pass.
    line_tops = []
    y = PAD
    for i, ln in enumerate(lines):
        line_tops.append(y)
        f = bold if is_prompt[i] else font
        c = PROMPT_FG if is_prompt[i] else FG
        d.text((PAD, y), ln, font=f, fill=c)
        y += LINE_H

    # Annotation pass: red ellipses + labels.
    for hl in highlights:
        target_y = None
        target_x0, target_x1 = PAD, PAD
        if "line" in hl:
            idx = hl["line"]
            if 0 <= idx < len(lines):
                target_y = line_tops[idx]
                target_x1 = PAD + d.textlength(lines[idx], font=font)
        elif "pattern" in hl:
            for idx, ln in enumerate(lines):
                if hl["pattern"] in ln:
                    target_y = line_tops[idx]
                    # Ellipse around the matched substring, not the whole line.
                    start = ln.find(hl["pattern"])
                    pre = ln[:start]
                    target_x0 = PAD + d.textlength(pre, font=font)
                    target_x1 = target_x0 + d.textlength(
                        hl["pattern"], font=font)
                    break
        if target_y is None:
            continue  # pattern not found — skip rather than mis-annotate
        pad = 6
        d.ellipse([target_x0 - pad, target_y - 3,
                   target_x1 + pad, target_y + LINE_H - 6],
                  outline=RED, width=3)
        # Label below-left of the ellipse (avoids covering the line above).
        label = hl.get("label", "")
        if label:
            tw = d.textlength(label, font=font)
            lx = max(PAD, min(target_x0, IMG_W - tw - PAD))
            ly = target_y + LINE_H - 2
            # Small dark pill behind the label for readability.
            d.rectangle([lx - 4, ly - 2, lx + tw + 4, ly + LINE_H - 6],
                        fill=(60, 10, 10))
            d.text((lx, ly), label, font=font, fill=(255, 150, 150))

    # Caption bar.
    cy = img_h - caption_h
    d.rectangle([0, cy, IMG_W, img_h], fill=CAPTION_BG)
    d.text((PAD, cy + 12), caption, font=font, fill=CAPTION_FG)

    out = OUT_DIR / out_name
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out} ({IMG_W}x{img_h})")


def main():
    caps = CAPTURE_DIR

    # 1. The one command: full pipeline success.
    # WHY ~/demo in the prompt: the real capture ran from /home/hatch/demo,
    # but the prompt shows the short form — what a user would actually type
    # sitting in their project folder. The output paths are real.
    full = (caps / "full_run.txt").read_text()
    render(
        "mesh-to-cad bracket_prismatic.stl",
        full,
        "Fig 1 — The one command. Three steps, clear verdicts, next steps at the end.",
        [
            {"pattern": "Step 1/3", "label": "steps are numbered"},
            {"pattern": "VERDICT: CLEAN", "label": "the verdict is the point"},
            {"pattern": "Pipeline complete", "label": "you're done here"},
        ],
        "01-full-pipeline.png",
    )

    # 2. Quality gate on a real scan-like file (benchy).
    benchy = (caps / "check_benchy.txt").read_text()
    render(
        "mesh-to-cad check benchy.stl",
        benchy,
        "Fig 2 — The quality gate on a real-world mesh. Four numbers, one verdict.",
        [
            {"pattern": "VERDICT:", "label": "read this first"},
            {"pattern": "components:", "label": "floating junk detector"},
        ],
        "02-quality-gate.png",
    )

    # 3. Friendly error: file not found.
    nf = (caps / "err_notfound.txt").read_text()
    render(
        "mesh-to-cad missing.stl",
        nf,
        "Fig 3 — File not found: says what's wrong and what to check. No traceback.",
        [
            {"pattern": "file not found", "label": "plain English"},
            {"pattern": "Check the path", "label": "tells you what to do"},
        ],
        "03-error-notfound.png",
    )

    # 4. Friendly error: wrong file type.
    wt = (caps / "err_wrongtype.txt").read_text()
    render(
        "mesh-to-cad notes.txt",
        wt,
        "Fig 4 — Wrong file type: explains why and how to fix it.",
        [
            {"pattern": "wrong file type", "label": "names the problem"},
            {"pattern": "export as .stl", "label": "gives the fix"},
        ],
        "04-error-wrongtype.png",
    )


if __name__ == "__main__":
    main()
