#!/usr/bin/env python3

import os
import sys
import argparse
import random
from pathlib import Path
import numpy as np
from PIL import Image

# Grid
ICON_SZ = 32
EDGE_D = 4
CANVAS_W = 50  # virtual canvas width
CANVAS_H = 20  # virtual canvas height
FINAL_W = 25  # Final output width
FINAL_H = 10  # Final output height
CELL_OUT = 64
BORDER = 2

# Weights
W_EDGE = 0.40
W_DIAG = 0.10
W_GLOB = 0.15
W_LUM = 0.15
W_MAGN = 0.20

MIN_PIX = 4
W_PERP = 0.60
W_AVG = 0.40

JUMP_THRESHOLD = 75.0

_OPP = {'left': 'right', 'right': 'left', 'top': 'bottom', 'bottom': 'top'}

_DIAG_CORNERS = {
    (-1, -1): (('top', 'left'), ('bottom', 'right')),
    (-1, 1): (('top', 'right'), ('bottom', 'left')),
    (1, -1): (('bottom', 'left'), ('top', 'right')),
    (1, 1): (('bottom', 'right'), ('top', 'left')),
}


def load_folder(folder):
    pngs = sorted(Path(folder).glob("*.png"))
    if not pngs:
        sys.exit(f"[error] No .png files found in: {folder!r}")

    print(f"Found {len(pngs)} images")
    icons = []
    for png in pngs:
        try:
            img = Image.open(png).resize((ICON_SZ, ICON_SZ), Image.LANCZOS).convert("RGBA")
            icons.append((png.stem, img))
        except Exception:
            pass

    if not icons:
        sys.exit("[error] Could not load any PNG images.")
    print(f"{len(icons)} images loaded successfully.\n")
    return icons


def _get_bbox(arr):
    mask = arr[..., 3] > 32
    if not mask.any():
        return 0, arr.shape[0] - 1, 0, arr.shape[1] - 1

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    rmin, rmax = np.argmax(rows), len(rows) - 1 - np.argmax(rows[::-1])
    cmin, cmax = np.argmax(cols), len(cols) - 1 - np.argmax(cols[::-1])
    return rmin, rmax, cmin, cmax


def _edge_strip(arr, side):
    """
    Return the edge strip along `side` of the icon array,
    seeping past any transparent pixels.
    """
    rmin, rmax, cmin, cmax = _get_bbox(arr)
    H, W = arr.shape[0], arr.shape[1]

    if side == 'left':
        start = min(cmin, W - EDGE_D)
        return arr[:, start: start + EDGE_D, :]
    if side == 'right':
        end = max(cmax, EDGE_D - 1)
        return arr[:, end - EDGE_D + 1: end + 1, :]
    if side == 'top':
        start = min(rmin, H - EDGE_D)
        return arr[start: start + EDGE_D, :, :]
    if side == 'bottom':
        end = max(rmax, EDGE_D - 1)
        return arr[end - EDGE_D + 1: end + 1, :, :]
    raise ValueError(f"Unknown side: {side!r}")


def _corner_block(arr, vert, horiz):
    """
    Return the EDGE_D × EDGE_D corner block of arr, snapping to opaque bounds.
    """
    rmin, rmax, cmin, cmax = _get_bbox(arr)
    H, W = arr.shape[0], arr.shape[1]

    r_start = min(rmin, H - EDGE_D) if vert == 'top' else max(rmax, EDGE_D - 1) - EDGE_D + 1
    c_start = min(cmin, W - EDGE_D) if horiz == 'left' else max(cmax, EDGE_D - 1) - EDGE_D + 1

    return arr[r_start: r_start + EDGE_D, c_start: c_start + EDGE_D, :]


def _strip_score(a, b):
    mask = (a[..., 3] > 32) & (b[..., 3] > 32)
    if mask.sum() < MIN_PIX: return 100.0
    ar = a[..., :3][mask].astype(np.float32)
    br = b[..., :3][mask].astype(np.float32)
    per_px = np.sqrt(((ar - br) ** 2).sum(axis=1)).mean()
    avg_col = np.sqrt(((ar.mean(0) - br.mean(0)) ** 2).sum())
    return (W_PERP * per_px + W_AVG * avg_col) / 441.0 * 255.0


def _global_score(a, b):
    def mean_col(arr):
        mask = arr[..., 3] > 32
        if not mask.any(): return np.array([128., 128., 128.], dtype=np.float32)
        return arr[..., :3][mask].mean(0).astype(np.float32)

    d = mean_col(a) - mean_col(b)
    return float(np.sqrt((d ** 2).sum())) / 441.0 * 255.0


def _mean_lum(arr):
    mask = arr[..., 3] > 32
    if not mask.any(): return 128.0
    rgb = arr[..., :3][mask]
    return (0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]).mean()


def precompute(arrays):
    n = len(arrays)
    sh, sv, gl = np.zeros((n, n), np.float32), np.zeros((n, n), np.float32), np.zeros((n, n), np.float32)
    print("Pre-computing scores")
    lums = np.array([_mean_lum(a) for a in arrays], dtype=np.float32)

    for i in range(n):
        ri, bi = _edge_strip(arrays[i], 'right'), _edge_strip(arrays[i], 'bottom')
        for j in range(n):
            if i == j: continue
            sh[i, j] = _strip_score(ri, _edge_strip(arrays[j], 'left'))
            sv[i, j] = _strip_score(bi, _edge_strip(arrays[j], 'top'))
            if i < j: gl[i, j] = gl[j, i] = _global_score(arrays[i], arrays[j])
        print(f"  image {i + 1:>3d}/{n}", end="\r")
    print(f"  {n}/{n} — done              ")
    return sh, sv, gl, lums


def _place_score(k, r, c, neighbours, sh, sv, gl, lums, arrays, placed_positions):
    edge_ss, diag_ss, glob_ss, lum_diffs = [], [], [], []
    for dr, dc, m in neighbours:
        glob_ss.append(float(gl[k, m]))
        lum_diffs.append(abs(lums[k] - lums[m]))
        is_edge = (dr == 0) != (dc == 0)
        if is_edge:
            if (dr, dc) == (0, 1):
                s = sh[k, m]
            elif (dr, dc) == (0, -1):
                s = sh[m, k]
            elif (dr, dc) == (-1, 0):
                s = sv[m, k]
            else:
                s = sv[k, m]
            edge_ss.append(s)
        else:
            (kv, kh), (mv, mh) = _DIAG_CORNERS[(dr, dc)]
            cb_k = _corner_block(arrays[k], kv, kh).reshape(-1, 4)
            cb_m = _corner_block(arrays[m], mv, mh).reshape(-1, 4)
            diag_ss.append(_strip_score(cb_k, cb_m))

    avg_e = float(np.mean(edge_ss)) if edge_ss else 0.0
    avg_d = float(np.mean(diag_ss)) if diag_ss else avg_e
    avg_g = float(np.mean(glob_ss)) if glob_ss else 0.0
    avg_l = float(np.mean(lum_diffs)) if lum_diffs else 0.0

    magnet_score = 0.0
    total_weight = 0.0
    for m, (mr, mc) in placed_positions.items():
        g_dist = float(gl[k, m])
        if g_dist < 100:
            weight = 100.0 - g_dist
            phys_dist = np.sqrt((r - mr) ** 2 + (c - mc) ** 2)
            magnet_score += phys_dist * weight
            total_weight += weight

    if total_weight > 0:
        magnet_score = (magnet_score / total_weight)
        magnet_score = (magnet_score / 35.0) * 255.0

    return (W_EDGE * avg_e) + (W_DIAG * avg_d) + (W_GLOB * avg_g) + (W_LUM * avg_l) + (W_MAGN * magnet_score)


_EDGE_DIRS = [(1, 0), (-1, 0), (0, -1), (0, 1)]  # Bottom, Top, Left, Right
_DIAG_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
_ALL_DIRS = _EDGE_DIRS + _DIAG_DIRS


def build_grid(icons, arrays, anchor_configs, sh, sv, gl, lums, chains_dict=None):
    if chains_dict is None: chains_dict = {}

    n = len(icons)

    # 1. Precompute chain offsets
    chain_offsets = {}
    chain_targets = set()
    for k in range(n):
        offsets = []
        curr = k
        r_off, c_off = 0, 0
        visited = set([k])
        while curr in chains_dict:
            nxt, d_name = chains_dict[curr]
            if nxt in visited: break
            if d_name == 'top':
                r_off -= 1
            elif d_name == 'bottom':
                r_off += 1
            elif d_name == 'left':
                c_off -= 1
            elif d_name == 'right':
                c_off += 1
            offsets.append((nxt, r_off, c_off))
            chain_targets.add(nxt)
            curr = nxt
            visited.add(nxt)
        if offsets:
            chain_offsets[k] = offsets

    grid = [[None] * CANVAS_W for _ in range(CANVAS_H)]
    remaining = set(range(n))

    placed_positions = {}
    frontier = []
    in_front = set()

    def push_edge_neighbors(r, c):
        for dr, dc in _EDGE_DIRS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < CANVAS_H and 0 <= nc < CANVAS_W and grid[nr][nc] is None and (nr, nc) not in in_front:
                in_front.add((nr, nc))
                frontier.append((nr, nc))

    placed = 0
    min_r, max_r, min_c, max_c = 999, -999, 999, -999

    def place_icon_and_chain(root_k, r, c):
        nonlocal placed, min_r, max_r, min_c, max_c
        to_place = [(root_k, r, c)]
        for m, dr, dc in chain_offsets.get(root_k, []):
            to_place.append((m, r + dr, c + dc))

        for m, mr, mc in to_place:
            if 0 <= mr < CANVAS_H and 0 <= mc < CANVAS_W and grid[mr][mc] is None:
                grid[mr][mc] = m
                if m in remaining: remaining.remove(m)
                placed_positions[m] = (mr, mc)
                placed += 1
                min_r, max_r = min(min_r, mr), max(max_r, mr)
                min_c, max_c = min(min_c, mc), max(max_c, mc)
                push_edge_neighbors(mr, mc)
                print(f"  {placed:>3d}/{n}  → {icons[m][0]!r:40s}", end="\r")

    # Place all starting anchors
    for idx, r, c in anchor_configs:
        if idx in remaining:
            place_icon_and_chain(idx, r, c)

    while frontier and remaining:
        selectable_remaining = remaining - chain_targets
        if not selectable_remaining:
            selectable_remaining = remaining

        best_overall_s = float('inf')
        best_k, best_r, best_c, best_f_idx = None, None, None, None

        for f_idx, (r, c) in enumerate(frontier):
            if grid[r][c] is not None: continue

            neighbours = []
            for dr, dc in _ALL_DIRS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < CANVAS_H and 0 <= nc < CANVAS_W and grid[nr][nc] is not None:
                    neighbours.append((dr, dc, grid[nr][nc]))

            edge_nbrs = [(dr, dc, m) for dr, dc, m in neighbours if dr == 0 or dc == 0]
            if not edge_nbrs: continue

            for k in selectable_remaining:
                chain_min_r, chain_max_r = r, r
                chain_min_c, chain_max_c = c, c
                fits = True
                for m, dr, dc in chain_offsets.get(k, []):
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < CANVAS_H and 0 <= nc < CANVAS_W) or grid[nr][nc] is not None:
                        fits = False;
                        break
                    chain_min_r = min(chain_min_r, nr)
                    chain_max_r = max(chain_max_r, nr)
                    chain_min_c = min(chain_min_c, nc)
                    chain_max_c = max(chain_max_c, nc)
                if not fits: continue

                if max(max_r, chain_max_r) - min(min_r, chain_min_r) + 1 > FINAL_H: continue
                if max(max_c, chain_max_c) - min(min_c, chain_min_c) + 1 > FINAL_W: continue

                s = _place_score(k, r, c, neighbours, sh, sv, gl, lums, arrays, placed_positions)
                if s < best_overall_s:
                    best_overall_s = s
                    best_k, best_r, best_c, best_f_idx = k, r, c, f_idx

        if (best_overall_s > JUMP_THRESHOLD and len(selectable_remaining) > 0) or best_k is None:
            shuffled_rem = list(selectable_remaining)
            random.shuffle(shuffled_rem)

            for k in shuffled_rem:
                spots = []
                for r in range(CANVAS_H):
                    for c in range(CANVAS_W):
                        if grid[r][c] is not None: continue

                        chain_min_r, chain_max_r = r, r
                        chain_min_c, chain_max_c = c, c
                        fits = True
                        for m, dr, dc in chain_offsets.get(k, []):
                            nr, nc = r + dr, c + dc
                            if not (0 <= nr < CANVAS_H and 0 <= nc < CANVAS_W) or grid[nr][nc] is not None:
                                fits = False;
                                break
                            chain_min_r = min(chain_min_r, nr)
                            chain_max_r = max(chain_max_r, nr)
                            chain_min_c = min(chain_min_c, nc)
                            chain_max_c = max(chain_max_c, nc)
                        if not fits: continue

                        if max(max_r, chain_max_r) - min(min_r, chain_min_r) + 1 > FINAL_H: continue
                        if max(max_c, chain_max_c) - min(min_c, chain_min_c) + 1 > FINAL_W: continue

                        spots.append((r, c))

                if spots:
                    best_r, best_c = random.choice(spots)
                    best_k = k
                    best_f_idx = None
                    break

        if best_k is None:
            break

        place_icon_and_chain(best_k, best_r, best_c)

        if best_f_idx is not None: frontier.pop(best_f_idx)

    print(f"\n  {placed} placed, {len(remaining)} unplaced.")

    # Find the bounding box to extract the final area
    placed_r = [r for r in range(CANVAS_H) for c in range(CANVAS_W) if grid[r][c] is not None]
    placed_c = [c for r in range(CANVAS_H) for c in range(CANVAS_W) if grid[r][c] is not None]

    fin_min_r = min(placed_r) if placed_r else 0
    fin_min_c = min(placed_c) if placed_c else 0

    final_grid = [[None] * FINAL_W for _ in range(FINAL_H)]
    for r in range(FINAL_H):
        for c in range(FINAL_W):
            src_r = fin_min_r + r
            src_c = fin_min_c + c
            if 0 <= src_r < CANVAS_H and 0 <= src_c < CANVAS_W:
                final_grid[r][c] = grid[src_r][src_c]

    return final_grid


def render(icons, grid, out_path):
    step = CELL_OUT + BORDER * 2
    W = FINAL_W * step + BORDER
    H = FINAL_H * step + BORDER
    out = Image.new('RGBA', (W, H), (24, 24, 24, 255))
    for r in range(FINAL_H):
        for c in range(FINAL_W):
            idx = grid[r][c]
            if idx is None: continue
            icon_img = icons[idx][1].resize((CELL_OUT, CELL_OUT), Image.NEAREST)
            x = c * step + BORDER
            y = r * step + BORDER
            out.paste(icon_img, (x, y), icon_img)
    out.save(out_path)
    print(f"\nSaved → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs='?', default=r"C:\Users\flori\Desktop\extracted_icons_java")
    ap.add_argument("--anchors", nargs='+', default=[],
                    help="List of icon names to use as starting anchors (e.g. Fortnite Rust)")
    ap.add_argument("--chain", action='append', nargs=3, help="Chain icons: src target direction")
    ap.add_argument("--output", default="image_gradient.png")
    args = ap.parse_args()

    icons = load_folder(args.folder)
    arrays = [np.array(img, dtype=np.float32) for _, img in icons]
    names = [n.lower() for n, _ in icons]

    # Process Chains
    chains_dict = {}
    if args.chain:
        for src_str, tgt_str, d_name in args.chain:
            src_name = Path(src_str).stem.lower()
            tgt_name = Path(tgt_str).stem.lower()
            try:
                src_idx = names.index(src_name)
                tgt_idx = names.index(tgt_name)
                chains_dict[src_idx] = (tgt_idx, d_name)
            except ValueError:
                print(f"  [!] Chain {src_str} -> {tgt_str} invalid: icon not found.")

    # Resolve Anchors
    V_MIN_R = (CANVAS_H - FINAL_H) // 2
    V_MAX_R = V_MIN_R + FINAL_H - 1
    V_MIN_C = (CANVAS_W - FINAL_W) // 2
    V_MAX_C = V_MIN_C + FINAL_W - 1
    MID_R = CANVAS_H // 2
    MID_C = CANVAS_W // 2

    anchor_configs = []
    if not args.anchors:
        # Default: 1 random seed in the middle
        anchor_configs.append((random.randrange(len(icons)), MID_R, MID_C))
    else:
        found_anchors = []
        for a in args.anchors:
            try:
                found_anchors.append(names.index(a.lower()))
            except ValueError:
                print(f"  [!] Anchor '{a}' not found! Ignoring.")

        num_a = len(found_anchors)
        if num_a == 1:
            anchor_configs.append((found_anchors[0], MID_R, MID_C))
        elif num_a == 2:  # Left and Right
            anchor_configs.append((found_anchors[0], MID_R, V_MIN_C + 2))
            anchor_configs.append((found_anchors[1], MID_R, V_MAX_C - 2))
        elif num_a == 3:  # Triangle (Top-Left, Top-Right, Bottom-Center)
            anchor_configs.append((found_anchors[0], V_MIN_R + 2, V_MIN_C + 2))
            anchor_configs.append((found_anchors[1], V_MIN_R + 2, V_MAX_C - 2))
            anchor_configs.append((found_anchors[2], V_MAX_R - 2, MID_C))
        elif num_a >= 4:  # Four Corners
            anchor_configs.append((found_anchors[0], V_MIN_R + 2, V_MIN_C + 2))
            anchor_configs.append((found_anchors[1], V_MIN_R + 2, V_MAX_C - 2))
            anchor_configs.append((found_anchors[2], V_MAX_R - 2, V_MIN_C + 2))
            anchor_configs.append((found_anchors[3], V_MAX_R - 2, V_MAX_C - 2))

    print(f"Virtual Canvas: {CANVAS_W} × {CANVAS_H} | Final Output: {FINAL_W} × {FINAL_H}")
    sh, sv, gl, lums = precompute(arrays)
    print("\nBuilding gradient grid")
    grid = build_grid(icons, arrays, anchor_configs, sh, sv, gl, lums, chains_dict)
    render(icons, grid, args.output)


if __name__ == "__main__":
    main()