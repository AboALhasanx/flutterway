import os
from PIL import Image, ImageDraw

def create_flutterway_icon(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Rounded Squircle Background (Deep Midnight Navy with Cyan Border)
    # Background rect
    corner_radius = 110
    draw.rounded_rectangle([16, 16, size - 16, size - 16], radius=corner_radius, fill="#0f172a", outline="#38bdf8", width=12)

    # Inner subtle glow ring
    draw.rounded_rectangle([32, 32, size - 32, size - 32], radius=corner_radius - 12, outline="#1e293b", width=6)

    # 2. Modern stylized Flutter bird / wings shape with bright gradients
    # Wing 1 (Flutter Cyan)
    pts_wing1 = [(150, 110), (390, 110), (270, 230), (150, 230)]
    draw.polygon(pts_wing1, fill="#38bdf8")

    # Wing 2 (Sky Blue)
    pts_wing2 = [(270, 230), (390, 230), (240, 380), (120, 380)]
    draw.polygon(pts_wing2, fill="#0284c7")

    # Android Green Jet / Accent
    pts_jet = [(240, 380), (360, 380), (410, 430), (290, 430)]
    draw.polygon(pts_jet, fill="#10b981")

    # Little golden rocket spark / lightning
    spark_center = (400, 140)
    draw.ellipse([spark_center[0] - 22, spark_center[1] - 22, spark_center[0] + 22, spark_center[1] + 22], fill="#fbbf24")

    # Save PNG
    png_path = os.path.join(output_dir, "icon.png")
    img.save(png_path, format="PNG")
    print(f"Saved PNG icon to {png_path}")

    # Save Multi-resolution ICO (16, 32, 48, 64, 128, 256)
    ico_path = os.path.join(output_dir, "icon.ico")
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print(f"Saved Multi-resolution ICO to {ico_path}")

if __name__ == "__main__":
    create_flutterway_icon(r"d:\flutterway\assets")
