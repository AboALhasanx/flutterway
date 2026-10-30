"""Generate FlutterWay app icons from the current transparent logo."""

import os

from PIL import Image, ImageDraw


def _trimmed_logo(path):
    image = Image.open(path).convert("RGBA")
    bbox = image.getbbox()
    return image.crop(bbox) if bbox else image


def create_flutterway_icon(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded app tile matching the in-app header logo.
    radius = 112
    draw.rounded_rectangle(
        [12, 12, size - 12, size - 12],
        radius=radius,
        fill="#111827",
        outline="#38bdf8",
        width=8,
    )

    logo = _trimmed_logo(os.path.join(output_dir, "logo_transparent.png"))
    target = int(size * 0.76)
    logo.thumbnail((target, target), Image.LANCZOS)
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2
    img.alpha_composite(logo, (x, y))

    png_path = os.path.join(output_dir, "icon.png")
    img.save(png_path, format="PNG")
    print(f"Saved PNG icon to {png_path}")

    ico_path = os.path.join(output_dir, "icon.ico")
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print(f"Saved multi-resolution ICO to {ico_path}")


if __name__ == "__main__":
    create_flutterway_icon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets"))
