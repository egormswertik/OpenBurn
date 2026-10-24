"""
§7: Raster Image Engine (PNG decode, Grayscale, Dithering, Pass-Through)
"""
import zlib
import struct
import math

def decode_png(png_bytes):
    """
    Standard PNG decoder using only struct and zlib.
    Supports 8-bit Gray, Truecolor (RGB), Indexed, Gray+Alpha, RGBA.
    """
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG header")
    idx = 8
    width = height = bit_depth = color_type = 0
    idat_chunks = []
    palette = []
    
    while idx < len(png_bytes):
        length = struct.unpack(">I", png_bytes[idx:idx+4])[0]
        chunk_type = png_bytes[idx+4:idx+8]
        data = png_bytes[idx+8:idx+8+length]
        idx += 12 + length

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", data)
            if bit_depth not in (8, 16):
                raise NotImplementedError(f"Unsupported bit depth: {bit_depth}")
            if interlace != 0:
                raise NotImplementedError("Interlacing not supported")
        elif chunk_type == b"PLTE":
            for i in range(0, len(data), 3):
                palette.append((data[i], data[i+1], data[i+2]))
        elif chunk_type == b"IDAT":
            idat_chunks.append(data)
        elif chunk_type == b"IEND":
            break

    raw = zlib.decompress(b"".join(idat_chunks))
    # Channels
    # 0: Gray, 2: RGB, 3: Indexed, 4: Gray+Alpha, 6: RGBA
    bpp = 1
    if color_type == 0: bpp = 1
    elif color_type == 2: bpp = 3
    elif color_type == 3: bpp = 1
    elif color_type == 4: bpp = 2
    elif color_type == 6: bpp = 4
    bytes_per_sample = 2 if bit_depth == 16 else 1
    bytes_per_pixel = bpp * bytes_per_sample

    stride = width * bytes_per_pixel
    img_data = [] # rows of (r, g, b, a)
    raw_idx = 0
    prev_row = bytearray(stride)

    for r in range(height):
        filter_type = raw[raw_idx]
        raw_idx += 1
        curr_row = bytearray(raw[raw_idx:raw_idx+stride])
        raw_idx += stride

        # Unfilter
        if filter_type == 0: # None
            pass
        elif filter_type == 1: # Sub
            for i in range(stride):
                left = curr_row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                curr_row[i] = (curr_row[i] + left) & 0xff
        elif filter_type == 2: # Up
            for i in range(stride):
                up = prev_row[i]
                curr_row[i] = (curr_row[i] + up) & 0xff
        elif filter_type == 3: # Average
            for i in range(stride):
                left = curr_row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = prev_row[i]
                curr_row[i] = (curr_row[i] + ((left + up) >> 1)) & 0xff
        elif filter_type == 4: # Paeth
            for i in range(stride):
                left = curr_row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                up = prev_row[i]
                up_left = prev_row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                # Paeth predictor
                p = left + up - up_left
                pa = abs(p - left)
                pb = abs(p - up)
                pc = abs(p - up_left)
                if pa <= pb and pa <= pc: pr = left
                elif pb <= pc: pr = up
                else: pr = up_left
                curr_row[i] = (curr_row[i] + pr) & 0xff
        prev_row = curr_row

        # Convert curr_row to RGBA
        row_pixels = []
        p_idx = 0
        for _ in range(width):
            if bit_depth == 16:
                # 16-bit normalized to 8-bit
                if color_type == 0:
                    val = curr_row[p_idx]; p_idx += 2
                    row_pixels.append((val, val, val, 255))
                elif color_type == 2:
                    r_val = curr_row[p_idx]; g_val = curr_row[p_idx+2]; b_val = curr_row[p_idx+4]
                    p_idx += 6
                    row_pixels.append((r_val, g_val, b_val, 255))
                elif color_type == 6:
                    r_val = curr_row[p_idx]; g_val = curr_row[p_idx+2]; b_val = curr_row[p_idx+4]; a_val = curr_row[p_idx+6]
                    p_idx += 8
                    row_pixels.append((r_val, g_val, b_val, a_val))
                else:
                    raise NotImplementedError()
            else:
                if color_type == 0:
                    val = curr_row[p_idx]; p_idx += 1
                    row_pixels.append((val, val, val, 255))
                elif color_type == 2:
                    row_pixels.append((curr_row[p_idx], curr_row[p_idx+1], curr_row[p_idx+2], 255))
                    p_idx += 3
                elif color_type == 3:
                    pal_entry = palette[curr_row[p_idx]]
                    p_idx += 1
                    row_pixels.append((pal_entry[0], pal_entry[1], pal_entry[2], 255))
                elif color_type == 4:
                    val = curr_row[p_idx]; a_val = curr_row[p_idx+1]
                    p_idx += 2
                    row_pixels.append((val, val, val, a_val))
                elif color_type == 6:
                    row_pixels.append((curr_row[p_idx], curr_row[p_idx+1], curr_row[p_idx+2], curr_row[p_idx+3]))
                    p_idx += 4
        img_data.append(row_pixels)

    return width, height, img_data

def to_grayscale(img_data):
    """
    §7.2:
    Y = round(0.299 * R + 0.587 * G + 0.114 * B)
    Pixels with Alpha < 128 treated as pure white (Y = 255).
    """
    height = len(img_data)
    width = len(img_data[0]) if height > 0 else 0
    gray = []
    for r in range(height):
        row = []
        for c in range(width):
            r_c, g_c, b_c, a_c = img_data[r][c]
            if a_c < 128:
                row.append(255)
            else:
                y = round(0.299 * r_c + 0.587 * g_c + 0.114 * b_c)
                row.append(max(0, min(255, y)))
        gray.append(row)
    return gray

def apply_dither(gray, mode, threshold=128):
    """
    §7.3, §7.5: Dithering algorithms
    Returns 2D grid of 0 (black/burn) and 255 (white/no-burn).
    """
    h = len(gray)
    w = len(gray[0]) if h > 0 else 0
    out = [[255]*w for _ in range(h)]

    if mode == "Threshold":
        for r in range(h):
            for c in range(w):
                out[r][c] = 0 if gray[r][c] < threshold else 255
        return out

    if mode == "Ordered":
        # 4x4 Bayer matrix
        bayer = [
            [ 0,  8,  2, 10],
            [12,  4, 14,  6],
            [ 3, 11,  1,  9],
            [15,  7, 13,  5]
        ]
        for r in range(h):
            for c in range(w):
                m_val = (bayer[r % 4][c % 4] + 0.5) * (255.0 / 16.0)
                out[r][c] = 0 if gray[r][c] < m_val else 255
        return out

    # Error diffusion: Floyd-Steinberg, Jarvis, Stucki, Atkinson
    # Working copy with float values
    buf = [[float(gray[r][c]) for c in range(w)] for r in range(h)]

    for y in range(h):
        # Serpentine (snake) traversal: left-to-right on even y, right-to-left on odd y
        is_forward = (y % 2 == 0)
        xs = range(w) if is_forward else range(w - 1, -1, -1)

        for x in xs:
            old_p = buf[y][x]
            new_p = 0.0 if old_p < 128.0 else 255.0
            out[y][x] = int(new_p)
            err = old_p - new_p

            if mode == "Floyd-Steinberg":
                # (x+1, y): 7/16; (x-1, y+1): 3/16; (x, y+1): 5/16; (x+1, y+1): 1/16
                dx = 1 if is_forward else -1
                def add_err(nx, ny, factor):
                    if 0 <= nx < w and 0 <= ny < h:
                        buf[ny][nx] += err * factor
                add_err(x + dx, y, 7.0 / 16.0)
                add_err(x - dx, y + 1, 3.0 / 16.0)
                add_err(x, y + 1, 5.0 / 16.0)
                add_err(x + dx, y + 1, 1.0 / 16.0)

            elif mode == "Atkinson":
                # 6/8 distributed
                dx = 1 if is_forward else -1
                def add_err(nx, ny):
                    if 0 <= nx < w and 0 <= ny < h:
                        buf[ny][nx] += err * (1.0 / 8.0)
                add_err(x + dx, y)
                add_err(x + 2*dx, y)
                add_err(x - dx, y + 1)
                add_err(x, y + 1)
                add_err(x + dx, y + 1)
                add_err(x, y + 2)

            elif mode == "Stucki":
                dx = 1 if is_forward else -1
                def add_err(nx, ny, factor):
                    if 0 <= nx < w and 0 <= ny < h:
                        buf[ny][nx] += err * (factor / 42.0)
                add_err(x + dx, y, 8)
                add_err(x + 2*dx, y, 4)
                add_err(x - 2*dx, y + 1, 2)
                add_err(x - dx, y + 1, 4)
                add_err(x, y + 1, 8)
                add_err(x + dx, y + 1, 4)
                add_err(x + 2*dx, y + 1, 2)
                add_err(x - 2*dx, y + 2, 1)
                add_err(x - dx, y + 2, 2)
                add_err(x, y + 2, 4)
                add_err(x + dx, y + 2, 2)
                add_err(x + 2*dx, y + 2, 1)

            elif mode == "Jarvis":
                dx = 1 if is_forward else -1
                def add_err(nx, ny, factor):
                    if 0 <= nx < w and 0 <= ny < h:
                        buf[ny][nx] += err * (factor / 48.0)
                add_err(x + dx, y, 7)
                add_err(x + 2*dx, y, 5)
                add_err(x - 2*dx, y + 1, 3)
                add_err(x - dx, y + 1, 5)
                add_err(x, y + 1, 7)
                add_err(x + dx, y + 1, 5)
                add_err(x + 2*dx, y + 1, 3)
                add_err(x - 2*dx, y + 2, 1)
                add_err(x - dx, y + 2, 3)
                add_err(x, y + 2, 5)
                add_err(x + dx, y + 2, 3)
                add_err(x + 2*dx, y + 2, 1)

    return out

def grayscale_to_power(gray_val, min_power, max_power, s_max):
    """
    §7.4:
    Points with Y = 255 excluded (S = 0).
    For Y in [0, 254]:
    S = round(S_min + ((254 - Y) / 254) * (S_max - S_min))
    where S_min = round(minPower * s_max / 100), S_max = round(maxPower * s_max / 100).
    """
    if gray_val >= 255:
        return 0
    s_min = round(min_power * s_max / 100.0)
    s_max_val = round(max_power * s_max / 100.0)
    return round(s_min + ((254.0 - gray_val) / 254.0) * (s_max_val - s_min))
