import os
import shutil
import configparser
import numpy as np
from PIL import Image
import random

try:
    import win32com.client
    from icoextract import IconExtractor

    CAN_EXTRACT = True
except ImportError:
    print("Icon extraction will be skipped.")
    CAN_EXTRACT = False


#------------------------------------------
#               CONFIG
# ------------------------------------------
DESKTOP_FOLDER = r"C:\Users\USER\Desktop"
EXTRACTED_FOLDER = r"C:\Users\USER\PycharmProjects\gradient\Extracted"
ICON_SIZE = 32
ALPHA_THRESHOLD = 128
MAX_GRID_WIDTH = 25
MAX_GRID_HEIGHT = 10
STARTING_ICON = "Counter-Strike 2.png" # leave it empty for random icon

# edge and corner priority
EDGE_WEIGHT = 0.25
CORNER_WEIGHT = 0.75


# ------------------------------------------
#          ICON EXTRACTION
# ------------------------------------------
def extract_icons(shortcut_folder, output_folder):
    """Reads .lnk and .url files and extracts the raw icon images to .png."""
    if not CAN_EXTRACT:
        return

    print("--- Starting Icon Extraction ---")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    shell = win32com.client.Dispatch("WScript.Shell")

    for filename in os.listdir(shortcut_folder):
        filepath = os.path.join(shortcut_folder, filename)
        safe_name = os.path.splitext(filename)[0]
        output_path = os.path.join(output_folder, f"{safe_name}.png")

        if os.path.exists(output_path):
            continue

        try:
            icon_source = None

            # Handle .lnk
            if filename.endswith(".lnk"):
                shortcut = shell.CreateShortCut(filepath)
                if shortcut.IconLocation and shortcut.IconLocation.split(',')[0]:
                    icon_source = shortcut.IconLocation.split(',')[0]
                else:
                    icon_source = shortcut.Targetpath

            # Handle .url
            elif filename.endswith(".url"):
                config = configparser.ConfigParser()
                config.read(filepath)
                if 'InternetShortcut' in config and 'IconFile' in config['InternetShortcut']:
                    icon_source = config['InternetShortcut']['IconFile']

            # Extract and Save
            if icon_source and os.path.exists(icon_source.strip('"')):
                icon_source = icon_source.strip('"')
                temp_ico = os.path.join(output_folder, f"temp_{safe_name}.ico")
                icon_to_open = None

                if icon_source.lower().endswith(('.exe', '.dll')):
                    extractor = IconExtractor(icon_source)
                    extractor.export_icon(temp_ico)
                    icon_to_open = temp_ico
                elif icon_source.lower().endswith('.ico'):
                    icon_to_open = icon_source

                if icon_to_open:
                    with Image.open(icon_to_open) as img:
                        img.seek(0)  # Grab highest resolution
                        img.resize((ICON_SIZE, ICON_SIZE)).save(output_path, "PNG")

                if os.path.exists(temp_ico):
                    os.remove(temp_ico)
                print(f" Extracted: {safe_name}")

        except Exception as e:
            pass

    print("--- Extraction Complete ---\n")


# -----------------------------------------
#                  LOGIC
# ------------------------------------------
def load_and_prep_images(folder):
    """Converts to RGBA to read transparent pxiels."""
    print("--- Loading Images for Math ---")
    images = {}
    for filename in os.listdir(folder):
        if filename.endswith('.png'):
            filepath = os.path.join(folder, filename)
            try:
                img = Image.open(filepath).convert('RGBA').resize((ICON_SIZE, ICON_SIZE))
                images[filename] = np.array(img, dtype=int)
            except Exception as e:
                print(f"Could not load {filename}: {e}")
    return images


def get_visible_edges(img_array):
    size = img_array.shape[0]
    edges = {
        'top': np.zeros((size, 3), dtype=int),
        'bottom': np.zeros((size, 3), dtype=int),
        'left': np.zeros((size, 3), dtype=int),
        'right': np.zeros((size, 3), dtype=int)
    }

    # Amount of pixels it checks
    MAX_SCAN_DEPTH = 5

    def extract_true_color(chunk):
        """Filters out black/white pixels to find the true color."""
        brightness = np.sum(chunk, axis=1)

        # Keep pixels that are not too dark (black outlines) and not too bright (white outlines)
        colorful_pixels = chunk[(brightness > 90) & (brightness < 720)]

        if len(colorful_pixels) >= 2:
            return np.median(colorful_pixels, axis=0)
        else:
            # If it's naturally a black/white icon, use normal median
            return np.median(chunk, axis=0)

    for i in range(size):
        # Top
        for y in range(size):
            if img_array[y, i, 3] > ALPHA_THRESHOLD:
                chunk = img_array[y:min(y + MAX_SCAN_DEPTH, size), i, :3]
                edges['top'][i] = extract_true_color(chunk)
                break
        # Bottom
        for y in range(size - 1, -1, -1):
            if img_array[y, i, 3] > ALPHA_THRESHOLD:
                start_y = max(y - MAX_SCAN_DEPTH + 1, 0)
                chunk = img_array[start_y:y + 1, i, :3]
                edges['bottom'][i] = extract_true_color(chunk)
                break
        # Left
        for x in range(size):
            if img_array[i, x, 3] > ALPHA_THRESHOLD:
                chunk = img_array[i, x:min(x + MAX_SCAN_DEPTH, size), :3]
                edges['left'][i] = extract_true_color(chunk)
                break
        # Right
        for x in range(size - 1, -1, -1):
            if img_array[i, x, 3] > ALPHA_THRESHOLD:
                start_x = max(x - MAX_SCAN_DEPTH + 1, 0)
                chunk = img_array[i, start_x:x + 1, :3]
                edges['right'][i] = extract_true_color(chunk)
                break

    CORNER_SAMPLE_SIZE = 5
    edges['top_left'] = np.median(edges['top'][:CORNER_SAMPLE_SIZE], axis=0)
    edges['top_right'] = np.median(edges['top'][-CORNER_SAMPLE_SIZE:], axis=0)
    edges['bottom_left'] = np.median(edges['bottom'][:CORNER_SAMPLE_SIZE], axis=0)
    edges['bottom_right'] = np.median(edges['bottom'][-CORNER_SAMPLE_SIZE:], axis=0)

    return edges


def calculate_edge_distance(edge1, edge2):
    """Pixel-by-pixel MSE comparison."""
    return np.sum((edge1 - edge2) ** 2)


def place_icons_on_grid(images, manual_seed=None):
    """Greedy Grid using Edge Caching"""

    print("--- 1. Caching Visible Edges ---")
    edge_cache = {}
    for img_name, img_array in images.items():
        edge_cache[img_name] = get_visible_edges(img_array)

    print(f"--- 2. Calculating Layout (Max Size: {MAX_GRID_WIDTH}x{MAX_GRID_HEIGHT}) ---")
    unplaced = list(images.keys())

    # Trim list if it exceeds grid capacity
    if len(unplaced) > (MAX_GRID_WIDTH * MAX_GRID_HEIGHT):
        unplaced = unplaced[:(MAX_GRID_WIDTH * MAX_GRID_HEIGHT)]

    if not unplaced:
        return {}

    grid = {}
    open_slots = set()

    def is_within_bounds(test_x, test_y):
        if not grid: return True
        all_x = [pos[0] for pos in grid.keys()] + [test_x]
        all_y = [pos[1] for pos in grid.keys()] + [test_y]
        curr_w = max(all_x) - min(all_x) + 1
        curr_h = max(all_y) - min(all_y) + 1
        return curr_w <= MAX_GRID_WIDTH and curr_h <= MAX_GRID_HEIGHT

    if manual_seed and manual_seed in unplaced:
        seed_name = manual_seed
        print(f"Starting with: {seed_name}")
    else:
        seed_name = random.choice(unplaced)
        print(f"Seed '{manual_seed}' not found. Using random: {seed_name}")

    # Place seed at center
    grid[(0, 0)] = seed_name
    unplaced.remove(seed_name)

    directions = [('top', 0, -1), ('bottom', 0, 1), ('left', -1, 0), ('right', 1, 0)]
    for _, dx, dy in directions:
        if is_within_bounds(dx, dy):
            open_slots.add((dx, dy))

    # --- PLACEMENT LOOP ---
    total_icons = len(unplaced)
    while unplaced and open_slots:
        best_match = None
        best_score = float('inf')

        for img_name in unplaced:
            img_edges = edge_cache[img_name]  # Grab pre-calculated edge

            for (x, y) in open_slots:
                current_slot_score = 0
                total_weight = 0  # Replaced neighbors_checked with total_weight

                # --- Check the 4 Flat Edges ---
                if (x, y - 1) in grid:  # Top neighbor
                    neighbor_edges = edge_cache[grid[(x, y - 1)]]
                    current_slot_score += calculate_edge_distance(img_edges['top'],
                                                                  neighbor_edges['bottom']) * EDGE_WEIGHT
                    total_weight += EDGE_WEIGHT
                if (x, y + 1) in grid:  # Bottom neighbor
                    neighbor_edges = edge_cache[grid[(x, y + 1)]]
                    current_slot_score += calculate_edge_distance(img_edges['bottom'],
                                                                  neighbor_edges['top']) * EDGE_WEIGHT
                    total_weight += EDGE_WEIGHT
                if (x - 1, y) in grid:  # Left neighbor
                    neighbor_edges = edge_cache[grid[(x - 1, y)]]
                    current_slot_score += calculate_edge_distance(img_edges['left'],
                                                                  neighbor_edges['right']) * EDGE_WEIGHT
                    total_weight += EDGE_WEIGHT
                if (x + 1, y) in grid:  # Right neighbor
                    neighbor_edges = edge_cache[grid[(x + 1, y)]]
                    current_slot_score += calculate_edge_distance(img_edges['right'],
                                                                  neighbor_edges['left']) * EDGE_WEIGHT
                    total_weight += EDGE_WEIGHT

                # --- Check the 4 Diagonal Corners ---
                if (x - 1, y - 1) in grid:  # Top-Left neighbor
                    neighbor_edges = edge_cache[grid[(x - 1, y - 1)]]
                    current_slot_score += calculate_edge_distance(img_edges['top_left'],
                                                                  neighbor_edges['bottom_right']) * CORNER_WEIGHT
                    total_weight += CORNER_WEIGHT
                if (x + 1, y - 1) in grid:  # Top-Right neighbor
                    neighbor_edges = edge_cache[grid[(x + 1, y - 1)]]
                    current_slot_score += calculate_edge_distance(img_edges['top_right'],
                                                                  neighbor_edges['bottom_left']) * CORNER_WEIGHT
                    total_weight += CORNER_WEIGHT
                if (x - 1, y + 1) in grid:  # Bottom-Left neighbor
                    neighbor_edges = edge_cache[grid[(x - 1, y + 1)]]
                    current_slot_score += calculate_edge_distance(img_edges['bottom_left'],
                                                                  neighbor_edges['top_right']) * CORNER_WEIGHT
                    total_weight += CORNER_WEIGHT
                if (x + 1, y + 1) in grid:  # Bottom-Right neighbor
                    neighbor_edges = edge_cache[grid[(x + 1, y + 1)]]
                    current_slot_score += calculate_edge_distance(img_edges['bottom_right'],
                                                                  neighbor_edges['top_left']) * CORNER_WEIGHT
                    total_weight += CORNER_WEIGHT

                # Average the score based on the weight of the neighbors
                if total_weight > 0:
                    current_slot_score /= total_weight

                if current_slot_score < best_score:
                    best_score = current_slot_score
                    best_match = (img_name, (x, y))

                if current_slot_score < best_score:
                    best_score = current_slot_score
                    best_match = (img_name, (x, y))

        if best_match:
            winner_name, (win_x, win_y) = best_match
            grid[(win_x, win_y)] = winner_name
            unplaced.remove(winner_name)
            open_slots.remove((win_x, win_y))

            for _, dx, dy in directions:
                new_x, new_y = win_x + dx, win_y + dy
                if (new_x, new_y) not in grid and is_within_bounds(new_x, new_y):
                    open_slots.add((new_x, new_y))

    return grid

# ------------------------------------------
#              RENDERING THE MAP
# ------------------------------------------
def render_final_grid(grid, extracted_folder):
    """Draws the final calculated grid into a single PNG map."""
    print("\n--- Rendering Final Map ---")
    if not grid:
        print("No grid to render.")
        return

    min_x = min(x for x, y in grid.keys())
    max_x = max(x for x, y in grid.keys())
    min_y = min(y for x, y in grid.keys())
    max_y = max(y for x, y in grid.keys())

    cols = (max_x - min_x) + 1
    rows = (max_y - min_y) + 1

    canvas_width = cols * ICON_SIZE
    canvas_height = rows * ICON_SIZE

    master_image = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))

    for (x, y), img_name in grid.items():
        img_path = os.path.join(extracted_folder, img_name)
        icon_img = Image.open(img_path).convert('RGBA').resize((ICON_SIZE, ICON_SIZE))

        paste_x = (x - min_x) * ICON_SIZE
        paste_y = (y - min_y) * ICON_SIZE

        master_image.paste(icon_img, (paste_x, paste_y), icon_img)  # 3rd argument keeps transparency

    master_image.save("final_desktop_gradient.png")
    print("Open 'final_desktop_gradient.png' to see your layout.")


# -----------------------------------------
#                   MAIN
# -----------------------------------------
if __name__ == "__main__":
    extract_icons(r"C:\Users\USER\Desktop", EXTRACTED_FOLDER)
    images = load_and_prep_images(EXTRACTED_FOLDER)

    if images:
        final_grid = place_icons_on_grid(images, manual_seed=STARTING_ICON)
        render_final_grid(final_grid, EXTRACTED_FOLDER)
    else:
        print("No images found to process")