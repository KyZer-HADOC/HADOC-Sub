from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "icon.jpg"
OUTPUT = ROOT / "icon.ico"
ICON_SIZE = 256


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Application icon source was not found: {SOURCE}")

    # Keep the full source image visible inside a square Windows icon canvas.
    with Image.open(SOURCE) as source:
        image = ImageOps.contain(
            source.convert("RGBA"),
            (ICON_SIZE, ICON_SIZE),
            method=Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        canvas.alpha_composite(
            image,
            ((ICON_SIZE - image.width) // 2, (ICON_SIZE - image.height) // 2),
        )

    canvas.save(
        OUTPUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    # Re-open the ICO so broken or empty output fails the build immediately.
    with Image.open(OUTPUT) as check:
        if check.format != "ICO":
            raise RuntimeError("Generated application icon is not a valid ICO file.")
        print(f"Created {OUTPUT.name} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
