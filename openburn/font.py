"""
Hershey-style Simplex Vector Stroke Font Generator
Renders arbitrary text strings into clean laser vector paths (lines and curves).
Zero dependencies.
"""
import math
from .geometry import XForm
from .project import Shape

# Simplified Hershey Simplex glyph strokes: 5x8 grid definitions
# Coordinate pairs [x, y], where negative x indicates pen-up / move-to
GLYPHS = {
    'A': [[0,0, 2,8, 4,0], [1,3, 3,3]],
    'B': [[0,0, 0,8, 3,8, 4,6, 3,4, 0,4], [3,4, 4,2, 3,0, 0,0]],
    'C': [[4,6, 2,8, 0,6, 0,2, 2,0, 4,2]],
    'D': [[0,0, 0,8, 2,8, 4,6, 4,2, 2,0, 0,0]],
    'E': [[4,8, 0,8, 0,0, 4,0], [0,4, 3,4]],
    'F': [[0,0, 0,8, 4,8], [0,4, 3,4]],
    'G': [[4,6, 2,8, 0,6, 0,2, 2,0, 4,0, 4,4, 2,4]],
    'H': [[0,0, 0,8], [4,0, 4,8], [0,4, 4,4]],
    'I': [[1,8, 3,8], [2,8, 2,0], [1,0, 3,0]],
    'J': [[3,8, 3,2, 2,0, 0,0, 0,2]],
    'K': [[0,0, 0,8], [4,8, 0,4, 4,0]],
    'L': [[0,8, 0,0, 4,0]],
    'M': [[0,0, 0,8, 2,4, 4,8, 4,0]],
    'N': [[0,0, 0,8, 4,0, 4,8]],
    'O': [[1,0, 0,2, 0,6, 1,8, 3,8, 4,6, 4,2, 3,0, 1,0]],
    'P': [[0,0, 0,8, 3,8, 4,6, 3,4, 0,4]],
    'Q': [[1,0, 0,2, 0,6, 1,8, 3,8, 4,6, 4,2, 3,0, 1,0], [2,2, 4,0]],
    'R': [[0,0, 0,8, 3,8, 4,6, 3,4, 0,4], [2,4, 4,0]],
    'S': [[4,6, 2,8, 0,6, 2,4, 4,2, 2,0, 0,2]],
    'T': [[0,8, 4,8], [2,8, 2,0]],
    'U': [[0,8, 0,2, 2,0, 4,2, 4,8]],
    'V': [[0,8, 2,0, 4,8]],
    'W': [[0,8, 1,0, 2,4, 3,0, 4,8]],
    'X': [[0,0, 4,8], [0,8, 4,0]],
    'Y': [[0,8, 2,4, 4,8], [2,4, 2,0]],
    'Z': [[0,8, 4,8, 0,0, 4,0]],
    '0': [[1,0, 0,2, 0,6, 1,8, 3,8, 4,6, 4,2, 3,0, 1,0], [0,2, 4,6]],
    '1': [[1,6, 2,8, 2,0], [0,0, 4,0]],
    '2': [[0,6, 2,8, 4,6, 4,4, 0,0, 4,0]],
    '3': [[0,8, 4,8, 2,5, 4,3, 4,1, 2,0, 0,0]],
    '4': [[3,0, 3,8, 0,3, 4,3]],
    '5': [[4,8, 0,8, 0,4, 3,4, 4,2, 3,0, 0,0]],
    '6': [[3,8, 1,8, 0,4, 0,2, 2,0, 4,2, 4,3, 2,4, 0,4]],
    '7': [[0,8, 4,8, 1,0]],
    '8': [[2,4, 0,6, 1,8, 3,8, 4,6, 2,4, 4,2, 3,0, 1,0, 0,2, 2,4]],
    '9': [[4,4, 2,4, 0,5, 0,6, 2,8, 4,6, 4,2, 2,0, 1,0]],
    '-': [[1,4, 3,4]],
    '+': [[1,4, 3,4], [2,2, 2,6]],
    '.': [[2,0, 2,1]],
    ':': [[2,2, 2,3], [2,5, 2,6]],
    ',': [[2,1, 1,0]],
    '!': [[2,3, 2,8], [2,0, 2,1]],
    '?': [[0,6, 2,8, 4,6, 3,4, 2,3], [2,0, 2,1]],
    '/': [[0,0, 4,8]],
    '_': [[0,0, 4,0]],
    ' ': []
}

def text_to_vector_shapes(text, x=10.0, y=10.0, height=10.0, cut_index=0):
    """
    Converts a text string into Path Shapes suitable for vector cutting/marking.
    `height` is the capital letter height in mm.
    """
    scale = height / 8.0
    char_width = 5.0 * scale
    char_spacing = 1.5 * scale
    
    shapes = []
    cursor_x = x
    
    for ch in text.upper():
        strokes = GLYPHS.get(ch, GLYPHS.get('?', []))
        if ch == ' ':
            cursor_x += char_width
            continue
            
        for stroke in strokes:
            # stroke is a flat list of [x0, y0, x1, y1, ...]
            pts = []
            for i in range(0, len(stroke), 2):
                px = cursor_x + stroke[i] * scale
                py = y + stroke[i+1] * scale
                pts.append((px, py))
            if len(pts) >= 2:
                shapes.append(Shape("Path", cut_index=cut_index, xform=XForm(), points=pts))
                
        cursor_x += char_width + char_spacing

    return shapes
