import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import subprocess
import os
import sys
import shutil
from PIL import Image, ImageTk, ImageEnhance


class GradientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Icon Gradient Generator")
        self.root.geometry("1200x800")
        self.root.configure(bg="#252525")

        # --- STATE ---
        self.selected_folder = None
        self.current_image = None
        self.original_image = None
        self.img_scale_ratio = 1.0

        self.brightness_modifiers = {}
        self.current_selected_icon = None
        self._ignore_slider = False

        # Chaining State
        self.chains = {}  # format: { 'source.png': {'target': 'target.png', 'dir': 'right'} }
        self.is_chain_selecting = False
        self.current_chain_target = None
        self.chain_center_img_ref = None

        # --- COLORS ---
        self.COLOR_LEFT_PANEL = "#403A36"
        self.COLOR_RIGHT_PANEL = "#1E1E1E"
        self.COLOR_BTN = "#6B605A"
        self.COLOR_BTN_HOVER = "#857871"
        self.COLOR_TEXT = "#E0E0E0"

        # --- LAYOUT ---
        self.left_panel = tk.Frame(root, bg=self.COLOR_LEFT_PANEL, width=320)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y)
        self.left_panel.pack_propagate(False)

        self.right_panel = tk.Frame(root, bg=self.COLOR_RIGHT_PANEL)
        self.right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.right_panel.bind("<Button-1>", lambda e: self.close_overlay())

        self.image_label = tk.Label(self.right_panel, bg=self.COLOR_RIGHT_PANEL)
        self.image_label.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
        self.image_label.bind("<Button-1>", self.on_image_click)

        # --- LEFT PANEL WIDGETS (MAIN) ---
        title_label = tk.Label(self.left_panel, text="Gradient Maker", font=("Segoe UI", 18, "bold"),
                               bg=self.COLOR_LEFT_PANEL, fg="white")
        title_label.pack(pady=(30, 20))

        self.btn_choose = self._create_button(self.left_panel, "Choose Folder", self.choose_folder)
        self.btn_choose.pack(pady=(10, 5), padx=20, fill=tk.X)

        self.lbl_folder = tk.Label(self.left_panel, text="No folder selected", font=("Segoe UI", 9, "italic"),
                                   bg=self.COLOR_LEFT_PANEL, fg="#A0A0A0", wraplength=260)
        self.lbl_folder.pack(pady=(0, 30), padx=10)

        self.btn_generate = self._create_button(self.left_panel, "Generate Gradient", self.start_generation)
        self.btn_generate.pack(pady=(10, 5), padx=20, fill=tk.X)
        self.btn_generate.config(state=tk.DISABLED)

        self.lbl_status = tk.Label(self.left_panel, text="", font=("Segoe UI", 11), bg=self.COLOR_LEFT_PANEL,
                                   fg="#4CAF50")
        self.lbl_status.pack(pady=20)

        # --- LEFT PANEL WIDGETS (OVERLAY) ---
        self.overlay_panel = tk.Frame(self.left_panel, bg=self.COLOR_LEFT_PANEL)

        tk.Label(self.overlay_panel, text="Icon Details", font=("Segoe UI", 16, "bold"), bg=self.COLOR_LEFT_PANEL,
                 fg="white").pack(pady=(20, 10))

        self.details_frame = tk.Frame(self.overlay_panel, bg=self.COLOR_LEFT_PANEL)
        self.details_frame.pack(pady=10)

        # Grid layout for the cross shape
        self.top_color_box = tk.Frame(self.details_frame, width=35, height=35, bg="black",
                                      highlightbackground="#1A1816", highlightthickness=2)
        self.top_color_box.grid(row=0, column=1, pady=(0, 10))

        self.left_color_box = tk.Frame(self.details_frame, width=35, height=35, bg="black",
                                       highlightbackground="#1A1816", highlightthickness=2)
        self.left_color_box.grid(row=1, column=0, padx=(0, 10))

        self.overlay_icon_lbl = tk.Label(self.details_frame, bg=self.COLOR_LEFT_PANEL)
        self.overlay_icon_lbl.grid(row=1, column=1)

        self.right_color_box = tk.Frame(self.details_frame, width=35, height=35, bg="black",
                                        highlightbackground="#1A1816", highlightthickness=2)
        self.right_color_box.grid(row=1, column=2, padx=(10, 0))

        self.bottom_color_box = tk.Frame(self.details_frame, width=35, height=35, bg="black",
                                         highlightbackground="#1A1816", highlightthickness=2)
        self.bottom_color_box.grid(row=2, column=1, pady=(10, 0))

        # Close Info
        self.lbl_close_info = tk.Label(self.overlay_panel, text="(Click empty space on\ngradient to close)",
                                       font=("Segoe UI", 9, "italic"), bg=self.COLOR_LEFT_PANEL, fg="#A0A0A0")
        self.lbl_close_info.pack(pady=(5, 10))

        # --- Brightness Controls ---
        self.brightness_frame = tk.Frame(self.overlay_panel, bg=self.COLOR_LEFT_PANEL)
        tk.Label(self.brightness_frame, text="Program Brightness Adjustment:", font=("Segoe UI", 10, "bold"),
                 bg=self.COLOR_LEFT_PANEL, fg="white").pack(pady=(5, 5))

        self.brightness_slider = tk.Scale(self.brightness_frame, from_=0.1, to=3.0, resolution=0.1,
                                          orient=tk.HORIZONTAL, bg=self.COLOR_LEFT_PANEL, fg="white",
                                          highlightthickness=0, command=self.on_brightness_change)
        self.brightness_slider.pack(fill=tk.X, padx=20)

        self.btn_reset_brightness = self._create_small_button(self.brightness_frame, "Reset Brightness",
                                                              self.reset_brightness)
        self.btn_reset_brightness.pack(pady=5)

        # --- Chaining Controls ---
        self.chaining_frame = tk.Frame(self.overlay_panel, bg=self.COLOR_LEFT_PANEL)
        tk.Label(self.chaining_frame, text="Chain with:", font=("Segoe UI", 10, "bold"), bg=self.COLOR_LEFT_PANEL,
                 fg="white").pack(pady=(10, 5))

        self.chain_grid = tk.Frame(self.chaining_frame, bg=self.COLOR_LEFT_PANEL)
        self.chain_grid.pack()

        arrow_font = ("Segoe UI", 12)

        self.btn_chain_top = tk.Button(self.chain_grid, text="▲", width=3, font=arrow_font, bg=self.COLOR_BTN,
                                       fg="white", relief=tk.FLAT, command=lambda: self.set_chain_dir('top'))
        self.btn_chain_left = tk.Button(self.chain_grid, text="◄", width=3, font=arrow_font, bg=self.COLOR_BTN,
                                        fg="white", relief=tk.FLAT, command=lambda: self.set_chain_dir('left'))
        self.btn_chain_right = tk.Button(self.chain_grid, text="►", width=3, font=arrow_font, bg=self.COLOR_BTN,
                                         fg="white", relief=tk.FLAT, command=lambda: self.set_chain_dir('right'))
        self.btn_chain_bottom = tk.Button(self.chain_grid, text="▼", width=3, font=arrow_font, bg=self.COLOR_BTN,
                                          fg="white", relief=tk.FLAT, command=lambda: self.set_chain_dir('bottom'))

        self.btn_chain_center = tk.Button(self.chain_grid, text="?", width=5, height=2, bg="#1E1E1E", fg="white",
                                          relief=tk.FLAT, cursor="hand2", command=self.start_chain_select)

        self.btn_chain_top.grid(row=0, column=1, pady=2)
        self.btn_chain_left.grid(row=1, column=0, padx=2)
        self.btn_chain_center.grid(row=1, column=1, padx=2, pady=2)
        self.btn_chain_right.grid(row=1, column=2, padx=2)
        self.btn_chain_bottom.grid(row=2, column=1, pady=2)

        self.chain_arrows = {
            'top': self.btn_chain_top,
            'left': self.btn_chain_left,
            'right': self.btn_chain_right,
            'bottom': self.btn_chain_bottom
        }

        self.lbl_chain_status = tk.Label(self.chaining_frame, text="", font=("Segoe UI", 9), bg=self.COLOR_LEFT_PANEL,
                                         fg="white")
        self.lbl_chain_status.pack(pady=2)

        self.btn_reset_chain = self._create_small_button(self.chaining_frame, "Reset Chain", self.reset_chain)
        self.btn_reset_chain.pack(pady=5)

    def _create_button(self, parent, text, command):
        btn = tk.Button(parent, text=text, command=command, font=("Segoe UI", 12, "bold"),
                        bg=self.COLOR_BTN, fg="white", activebackground=self.COLOR_BTN_HOVER,
                        activeforeground="white", relief=tk.FLAT, pady=8, cursor="hand2")
        btn.bind("<Enter>", lambda e: btn.config(bg=self.COLOR_BTN_HOVER) if btn['state'] != tk.DISABLED and btn[
            'bg'] != "#4CAF50" else None)
        btn.bind("<Leave>", lambda e: btn.config(bg=self.COLOR_BTN) if btn['state'] != tk.DISABLED and btn[
            'bg'] != "#4CAF50" else None)
        return btn

    def _create_small_button(self, parent, text, command):
        btn = tk.Button(parent, text=text, command=command, font=("Segoe UI", 9, "bold"),
                        bg=self.COLOR_BTN, fg="white", activebackground=self.COLOR_BTN_HOVER,
                        activeforeground="white", relief=tk.FLAT, pady=4, cursor="hand2")
        btn.bind("<Enter>", lambda e: btn.config(bg=self.COLOR_BTN_HOVER) if btn['state'] != tk.DISABLED else None)
        btn.bind("<Leave>", lambda e: btn.config(bg=self.COLOR_BTN) if btn['state'] != tk.DISABLED else None)
        return btn

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing shortcuts (.lnk/.url)")
        if folder:
            self.selected_folder = folder
            self.lbl_folder.config(text=folder, fg=self.COLOR_TEXT)
            self.btn_generate.config(state=tk.NORMAL)
            self.lbl_status.config(text="")

    def start_generation(self):
        if not self.selected_folder:
            return

        self.btn_choose.config(state=tk.DISABLED)
        self.btn_generate.config(state=tk.DISABLED)
        self.image_label.config(image="")
        self.close_overlay()

        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        extracted_original_dir = os.path.join(base_dir, "extracted_icons_original")
        extracted_auto_dir = os.path.join(base_dir, "extracted_icons_auto")
        output_img = os.path.join(base_dir, "image_gradient.png")

        # 1. Run Extractor (to original folder)
        self._update_status("Step 1/3: Extracting icons...\n(Check console for details)", "yellow")
        try:
            subprocess.run([sys.executable, "extractor.py", self.selected_folder, extracted_original_dir], check=True)
        except subprocess.CalledProcessError:
            self._update_status("Error: Extraction failed!", "red")
            self._unlock_ui()
            return

        # 2. Apply Brightness Modifiers
        self._update_status("Step 2/3: Applying filters...", "yellow")
        if not os.path.exists(extracted_auto_dir):
            os.makedirs(extracted_auto_dir)

        for f in os.listdir(extracted_auto_dir):
            try:
                os.remove(os.path.join(extracted_auto_dir, f))
            except:
                pass

        for file in os.listdir(extracted_original_dir):
            if file.endswith(".png"):
                src = os.path.join(extracted_original_dir, file)
                dst = os.path.join(extracted_auto_dir, file)
                mod = self.brightness_modifiers.get(file, 1.0)

                if mod != 1.0:
                    try:
                        img = Image.open(src).convert("RGBA")
                        r, g, b, a = img.split()
                        rgb_img = Image.merge("RGB", (r, g, b))
                        enhancer = ImageEnhance.Brightness(rgb_img)
                        rgb_img = enhancer.enhance(mod)
                        r2, g2, b2 = rgb_img.split()
                        img = Image.merge("RGBA", (r2, g2, b2, a))
                        img.save(dst)
                    except Exception as e:
                        print(f"Error modifying brightness for {file}: {e}")
                        shutil.copy2(src, dst)
                else:
                    shutil.copy2(src, dst)

        # 3. Run Gradient Builder
        self._update_status("Step 3/3: Building gradient...\n(Check console for details)", "yellow")

        # Build command with any saved chains
        cmd = [sys.executable, "icon_gradient.py", extracted_auto_dir, "--output", output_img]
        for src_icon, data in self.chains.items():
            cmd.extend(["--chain", src_icon, data['target'], data['dir']])

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            self._update_status("Error: Gradient generation failed", "red")
            self._unlock_ui()
            return

        # 4. Finish
        self._update_status("Gradient generated successfully.", "#4CAF50")
        self._display_image(output_img)
        self._unlock_ui()

    def _update_status(self, text, color):
        self.root.after(0, lambda: self.lbl_status.config(text=text, fg=color))

    def _unlock_ui(self):
        self.root.after(0, lambda: self.btn_choose.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.btn_generate.config(state=tk.NORMAL))

    def _display_image(self, path):
        def _load_and_show():
            if os.path.exists(path):
                img = Image.open(path).convert("RGBA")
                self.original_image = img.copy()
                img_w, img_h = img.size

                self.right_panel.update_idletasks()
                p_width = self.image_label.winfo_width()
                p_height = self.image_label.winfo_height()

                if p_width < 100 or p_height < 100:
                    p_width, p_height = 800, 600

                ratio = min(p_width / img_w, p_height / img_h)
                self.img_scale_ratio = ratio

                new_w, new_h = int(img_w * ratio), int(img_h * ratio)

                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.current_image = ImageTk.PhotoImage(img_resized)
                self.image_label.config(image=self.current_image)

        self.root.after(0, _load_and_show)

    def on_image_click(self, event):
        if not self.original_image:
            self.close_overlay()
            return

        lbl_w = self.image_label.winfo_width()
        lbl_h = self.image_label.winfo_height()
        disp_w = int(self.original_image.width * self.img_scale_ratio)
        disp_h = int(self.original_image.height * self.img_scale_ratio)

        offset_x = (lbl_w - disp_w) // 2
        offset_y = (lbl_h - disp_h) // 2

        if offset_x <= event.x <= offset_x + disp_w and offset_y <= event.y <= offset_y + disp_h:
            orig_x = (event.x - offset_x) / self.img_scale_ratio
            orig_y = (event.y - offset_y) / self.img_scale_ratio

            BORDER = 2
            CELL_OUT = 64
            STEP = CELL_OUT + BORDER * 2

            col = int((orig_x - BORDER) // STEP)
            row = int((orig_y - BORDER) // STEP)

            if 0 <= col < 25 and 0 <= row < 10:
                left = col * STEP + BORDER
                top = row * STEP + BORDER

                cell_img = self.original_image.crop((left, top, left + CELL_OUT, top + CELL_OUT))

                colors = cell_img.getcolors(maxcolors=1)
                is_empty = colors and len(colors) == 1 and colors[0][1][:3] == (24, 24, 24)

                if self.is_chain_selecting:
                    if is_empty:
                        self.lbl_chain_status.config(text="Selection cancelled", fg="red")
                    else:
                        target_file = self.find_matching_icon(cell_img)
                        if target_file and target_file != self.current_selected_icon:
                            self.current_chain_target = target_file
                            self.load_chain_center_img(target_file)
                            self.lbl_chain_status.config(text="Now select a direction", fg="yellow")
                        elif target_file == self.current_selected_icon:
                            self.lbl_chain_status.config(text="Cannot chain to itself!", fg="red")
                        else:
                            self.lbl_chain_status.config(text="Invalid selection", fg="red")

                    self.is_chain_selecting = False
                    return

                if is_empty:
                    self.close_overlay()
                else:
                    self.open_overlay(cell_img)
            else:
                if self.is_chain_selecting:
                    self.is_chain_selecting = False
                    self.lbl_chain_status.config(text="Selection cancelled", fg="red")
                self.close_overlay()
        else:
            if self.is_chain_selecting:
                self.is_chain_selecting = False
                self.lbl_chain_status.config(text="Selection cancelled", fg="red")
            self.close_overlay()

    def find_matching_icon(self, cell_img):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        extracted_auto_dir = os.path.join(base_dir, "extracted_icons_auto")
        if not os.path.exists(extracted_auto_dir): return None

        cell_rgb = cell_img.convert("RGB")
        cell_data = list(cell_rgb.getdata())
        best_match = None
        min_diff = float('inf')

        for file in os.listdir(extracted_auto_dir):
            if file.endswith(".png"):
                path = os.path.join(extracted_auto_dir, file)
                try:
                    img = Image.open(path).convert("RGBA")
                    img_32 = img.resize((32, 32), Image.Resampling.LANCZOS)
                    img_64 = img_32.resize((64, 64), Image.Resampling.NEAREST)
                    img_rgba_data = list(img_64.getdata())

                    diff = 0
                    valid_pixels = 0
                    for i in range(0, 4096, 41):
                        r2, g2, b2, a2 = img_rgba_data[i]
                        if a2 > 32:
                            r1, g1, b1 = cell_data[i]
                            diff += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
                            valid_pixels += 1

                    if valid_pixels > 0:
                        avg_diff = diff / valid_pixels
                        if avg_diff < min_diff:
                            min_diff = avg_diff
                            best_match = file
                except Exception:
                    pass

        if min_diff < 40:
            return best_match
        return None

    def open_overlay(self, cell_img):
        icon_filename = self.find_matching_icon(cell_img)
        self.is_chain_selecting = False  # Cancel any active chaining when a new icon is opened

        if not icon_filename:
            self.current_selected_icon = None
            self.show_overlay_visuals(cell_img)
            self.brightness_frame.pack_forget()
            self.chaining_frame.pack_forget()
        else:
            self.current_selected_icon = icon_filename

            # Sync slider state
            self._ignore_slider = True
            self.brightness_slider.set(self.brightness_modifiers.get(icon_filename, 1.0))
            self._ignore_slider = False

            # Sync Chain State
            if icon_filename in self.chains:
                c_data = self.chains[icon_filename]
                self.current_chain_target = c_data['target']
                self.load_chain_center_img(c_data['target'])
                self._update_arrow_colors(c_data['dir'])
                self.lbl_chain_status.config(text="Active Chain", fg="#4CAF50")
            else:
                self.current_chain_target = None
                self.btn_chain_center.config(image='', text="?", width=5, height=2)
                self._update_arrow_colors(None)
                self.lbl_chain_status.config(text="", fg="white")

            self.brightness_frame.pack(pady=10, fill=tk.X)
            self.chaining_frame.pack(pady=5, fill=tk.X)
            self.update_overlay_preview()

        self.overlay_panel.place(x=0, y=0, relwidth=1, relheight=1)
        self.overlay_panel.lift()

    def update_overlay_preview(self):
        if not self.current_selected_icon: return

        base_dir = os.path.dirname(os.path.abspath(__file__))
        original_path = os.path.join(base_dir, "extracted_icons_original", self.current_selected_icon)
        if not os.path.exists(original_path): return

        mod = self.brightness_modifiers.get(self.current_selected_icon, 1.0)
        img = Image.open(original_path).convert("RGBA")

        if mod != 1.0:
            r, g, b, a = img.split()
            rgb_img = Image.merge("RGB", (r, g, b))
            enhancer = ImageEnhance.Brightness(rgb_img)
            rgb_img = enhancer.enhance(mod)
            r2, g2, b2 = rgb_img.split()
            img = Image.merge("RGBA", (r2, g2, b2, a))

        img_32 = img.resize((32, 32), Image.Resampling.LANCZOS)
        cell_img = img_32.resize((64, 64), Image.Resampling.NEAREST)

        self.show_overlay_visuals(cell_img)

    def show_overlay_visuals(self, cell_img):
        bbox = cell_img.getbbox()
        if bbox is None:
            bbox = (0, 0, cell_img.width, cell_img.height)

        left, top, right, bottom = bbox
        depth = 12
        w, h = cell_img.size

        l_start = min(left, max(0, w - depth))
        r_end = max(right, min(w, depth))
        t_start = min(top, max(0, h - depth))
        b_end = max(bottom, min(h, depth))

        left_strip = cell_img.crop((l_start, 0, l_start + depth, h))
        right_strip = cell_img.crop((r_end - depth, 0, r_end, h))
        top_strip = cell_img.crop((0, t_start, w, t_start + depth))
        bottom_strip = cell_img.crop((0, b_end - depth, w, b_end))

        left_color = self.get_average_color(left_strip)
        right_color = self.get_average_color(right_strip)
        top_color = self.get_average_color(top_strip)
        bottom_color = self.get_average_color(bottom_strip)

        display_img = cell_img.resize((96, 96), Image.Resampling.NEAREST)
        self.overlay_icon_img = ImageTk.PhotoImage(display_img)

        self.overlay_icon_lbl.config(image=self.overlay_icon_img)
        self.left_color_box.config(bg=left_color)
        self.right_color_box.config(bg=right_color)
        self.top_color_box.config(bg=top_color)
        self.bottom_color_box.config(bg=bottom_color)

    # --- Brightness Handlers ---
    def on_brightness_change(self, val):
        if getattr(self, '_ignore_slider', False) or not self.current_selected_icon:
            return
        self.brightness_modifiers[self.current_selected_icon] = float(val)
        self.update_overlay_preview()

    def reset_brightness(self):
        if self.current_selected_icon:
            self._ignore_slider = True
            self.brightness_slider.set(1.0)
            self._ignore_slider = False
            self.brightness_modifiers[self.current_selected_icon] = 1.0
            self.update_overlay_preview()

    # --- Chaining Handlers ---
    def start_chain_select(self):
        self.is_chain_selecting = True
        self.lbl_chain_status.config(text="Click an icon on the right...", fg="yellow")

    def load_chain_center_img(self, filename):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, "extracted_icons_auto", filename)
        if os.path.exists(path):
            img = Image.open(path).convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
            self.chain_center_img_ref = ImageTk.PhotoImage(img)
            self.btn_chain_center.config(image=self.chain_center_img_ref, text="", width=40, height=40)

    def set_chain_dir(self, direction):
        if not self.current_chain_target:
            self.lbl_chain_status.config(text="Select an icon to chain first!", fg="red")
            return

        self.chains[self.current_selected_icon] = {'target': self.current_chain_target, 'dir': direction}
        self._update_arrow_colors(direction)
        self.lbl_chain_status.config(text="Chain saved!", fg="#4CAF50")

    def reset_chain(self):
        if self.current_selected_icon in self.chains:
            del self.chains[self.current_selected_icon]

        self.current_chain_target = None
        self.is_chain_selecting = False
        self.btn_chain_center.config(image='', text="?", width=5, height=2)
        self._update_arrow_colors(None)
        self.lbl_chain_status.config(text="Chain removed.", fg="#A0A0A0")

    def _update_arrow_colors(self, active_dir):
        for d, btn in self.chain_arrows.items():
            if d == active_dir:
                btn.config(bg="#4CAF50")
            else:
                btn.config(bg=self.COLOR_BTN)

    # --- Utils ---
    def get_average_color(self, image_slice):
        data = list(image_slice.getdata())
        valid_pixels = []

        for px in data:
            if len(px) == 4 and px[3] <= 32:
                continue
            if 20 <= px[0] <= 28 and 20 <= px[1] <= 28 and 20 <= px[2] <= 28:
                continue
            valid_pixels.append(px[:3])

        if not valid_pixels:
            return "#181818"

        bright_pixels = [p for p in valid_pixels if p[0] > 40 or p[1] > 40 or p[2] > 40]
        if bright_pixels:
            valid_pixels = bright_pixels

        r = sum(p[0] for p in valid_pixels)
        g = sum(p[1] for p in valid_pixels)
        b = sum(p[2] for p in valid_pixels)
        count = len(valid_pixels)

        return f"#{int(r / count):02x}{int(g / count):02x}{int(b / count):02x}"

    def close_overlay(self):
        self.overlay_panel.place_forget()


if __name__ == "__main__":
    root = tk.Tk()
    app = GradientGUI(root)
    root.mainloop()