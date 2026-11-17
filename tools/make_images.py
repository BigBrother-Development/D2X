"""Writes assets/icon.png (README logo) and assets/social-preview.png (GitHub social preview, 1280x640)."""
import os, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from icon import make_icon

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
make_icon(256).save(os.path.join(root, "assets", "icon.png"))

W, H = 1280, 640
img = Image.new("RGB", (W, H), (31, 78, 140))
d = ImageDraw.Draw(img)
icon = make_icon(360)
img.paste(icon, (130, (H - 360) // 2), icon)


def font(size, bold=True):
    for name in ("arialbd.ttf" if bold else "arial.ttf", "segoeuib.ttf" if bold else "segoeui.ttf"):
        try:
            return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name), size)
        except OSError:
            pass
    return ImageFont.load_default()


d.text((560, 190), "D2X", font=font(150), fill=(255, 255, 255))
d.text((566, 360), "DInput to XInput", font=font(52), fill=(255, 255, 255))
d.text((566, 435), "Use any gamepad as an Xbox 360 controller", font=font(30, False), fill=(200, 220, 245))
img.save(os.path.join(root, "assets", "social-preview.png"))
print("ok")
