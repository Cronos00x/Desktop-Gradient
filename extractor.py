import os
import sys
import argparse
import tempfile
import configparser
from pathlib import Path
from PIL import Image

try:
    import win32com.client
    from icoextract import IconExtractor
except ImportError:
    sys.exit("[!] Please run: pip install pywin32 pillow icoextract")


def get_target_path(shortcut_path):
    path_str = str(shortcut_path)
    if path_str.lower().endswith(".url"):
        try:
            config = configparser.ConfigParser()
            config.read(path_str)
            if 'InternetShortcut' in config and 'IconFile' in config['InternetShortcut']:
                return config['InternetShortcut']['IconFile']
        except Exception:
            return None
    elif path_str.lower().endswith(".lnk"):
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(path_str)

            if shortcut.IconLocation:
                icon_path = shortcut.IconLocation.split(',')[0]
                if os.path.exists(icon_path):
                    return icon_path

            if shortcut.TargetPath and os.path.exists(shortcut.TargetPath):
                return shortcut.TargetPath
        except Exception:
            return None

    return None


def process_shortcut(shortcut_path, output_dir):
    target_path = get_target_path(shortcut_path)
    if not target_path or not os.path.exists(target_path):
        print(f"  ✗ Could not resolve target for: {shortcut_path.name}")
        return False

    target_lower = target_path.lower()
    png_name = f"{shortcut_path.stem}.png"
    out_png_path = os.path.join(output_dir, png_name)
    temp_ico = os.path.join(tempfile.gettempdir(), "temp_icon_extract.ico")

    try:
        if target_lower.endswith('.exe') or target_lower.endswith('.dll'):
            extractor = IconExtractor(target_path)
            extractor.export_icon(temp_ico)
            icon_to_open = temp_ico
        elif target_lower.endswith('.ico'):
            icon_to_open = target_path
        else:
            print(f"  ✗ Unsupported target file type for: {shortcut_path.name}")
            return False

        with Image.open(icon_to_open) as img:
            img.save(out_png_path, format="PNG")

        print(f"   Saved icon: {png_name}")

        if os.path.exists(temp_ico):
            os.remove(temp_ico)

        return True

    except Exception as e:
        print(f"  ✗ Failed to extract {shortcut_path.name}: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="Extract high-res icons from Desktop shortcuts.")
    ap.add_argument("input_folder", nargs='?', default=r"C:\Users\flori\Desktop\pray1",
                    help="Folder containing .lnk or .url files")
    ap.add_argument("output_folder", nargs='?', default=r"C:\Users\flori\Desktop\extracted_icons",
                    help="Output folder for PNGs")
    args = ap.parse_args()

    input_dir = Path(args.input_folder)
    output_dir = Path(args.output_folder)

    if not input_dir.exists() or not input_dir.is_dir():
        sys.exit(f"Input folder not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning: {input_dir}")
    print(f"Saving to: {output_dir}")

    success = 0
    failed = 0

    for file in input_dir.iterdir():
        if file.suffix.lower() in ['.lnk', '.url']:
            if process_shortcut(file, output_dir):
                success += 1
            else:
                failed += 1

    print(f"Summary: {success} extracted, {failed} failed")


if __name__ == "__main__":
    main()