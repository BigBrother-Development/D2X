"""Draws the app icon (used for the window, the tray and the EXE icon)."""
from PIL import Image, ImageDraw


def make_icon(size=256):
    s = size / 256.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1):
        return [x0 * s, y0 * s, x1 * s, y1 * s]

    d.rounded_rectangle(box(8, 8, 248, 248), radius=int(48 * s), fill=(31, 78, 140, 255))
    white = (255, 255, 255, 255)
    # controller body
    d.rounded_rectangle(box(36, 88, 220, 170), radius=int(40 * s), fill=white)
    d.ellipse(box(30, 110, 92, 206), fill=white)
    d.ellipse(box(164, 110, 226, 206), fill=white)
    blue = (31, 78, 140, 255)
    # d-pad
    d.rectangle(box(70, 114, 84, 146), fill=blue)
    d.rectangle(box(61, 123, 93, 137), fill=blue)
    # face buttons
    for cx, cy in ((178, 116), (200, 130), (178, 144), (156, 130)):
        d.ellipse(box(cx - 7, cy - 7, cx + 7, cy + 7), fill=blue)
    return img


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    make_icon(256).save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out)
