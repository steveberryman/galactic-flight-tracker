# resize_logos.py
import sys, os
from PIL import Image

def main(src_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        if not name.lower().endswith(".png"):
            continue
        in_path = os.path.join(src_dir, name)
        img = Image.open(in_path).convert("RGBA")
        w, h = img.size
        if w == 0 or h == 0:
            continue
        scale = min(11 / w, 11 / h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (11, 11), (0, 0, 0, 0))
        off_x = (11 - new_w) // 2
        off_y = (11 - new_h) // 2
        canvas.paste(resized, (off_x, off_y), resized)
        out_path = os.path.join(out_dir, os.path.splitext(name)[0].upper() + ".png")
        canvas.save(out_path, optimize=True)
        print(f"Wrote {out_path}")

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "logos_src"
    out = sys.argv[2] if len(sys.argv) > 2 else "logos"
    main(src, out)