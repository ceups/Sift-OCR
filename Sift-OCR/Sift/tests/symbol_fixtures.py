"""Small text, punctuation, Spanish, and mathematical notation regressions."""
from PIL import Image, ImageDraw, ImageFont

CASES = [
    ("tiny-text", "Small text should still be readable.", 9, "segoeui.ttf", False, "text"),
    ("tiny-dark", "Read the small print: total $19.95.", 10, "segoeui.ttf", True, "text"),
    ("small-brackets", "items[0] = (count + 2);", 11, "consola.ttf", False, "text"),
    ("nested-brackets", "[(a + b) / (c - d)]", 14, "consola.ttf", False, "text"),
    ("bracket-pairs", "() [] {} (x) [y] {z}", 16, "consola.ttf", True, "text"),
    ("code-brackets", "if (items[2] >= 10) { return [x, y]; }", 12, "consola.ttf", False, "text"),
    ("spanish-small", "¿Cómo estás? ¡Mañana será un buen día!", 12, "segoeui.ttf", False, "spanish"),
    ("spanish-accents", "El niño pidió café, té y azúcar. ¡Qué alegría!", 16, "arial.ttf", False, "spanish"),
    ("spanish-dark", "Información: pingüino, año, corazón y acción.", 14, "segoeui.ttf", True, "spanish"),
    ("arithmetic", "(2 + 3) × 4 = 20", 24, "cambria.ttc", False, "math"),
    ("division", "12 ÷ 3 = 4", 24, "cambria.ttc", False, "math"),
    ("plus-minus", "x = 5 ± 0.2", 24, "cambria.ttc", False, "math"),
    ("inequalities", "0 ≤ x ≤ 10", 24, "cambria.ttc", False, "math"),
    ("root", "√16 = 4", 24, "cambria.ttc", False, "math"),
    ("math-brackets", "f(x) = [x + 2] / (x - 1)", 20, "cambria.ttc", False, "math"),
    ("math-greek", "π ≈ 3.14159", 24, "cambria.ttc", False, "math"),
]


def fixture(text, size, font, dark):
    face = ImageFont.truetype("C:/Windows/Fonts/" + font, size)
    bbox = face.getbbox(text)
    image = Image.new("RGB", (bbox[2] - bbox[0] + 20, bbox[3] - bbox[1] + 20), "#161616" if dark else "white")
    ImageDraw.Draw(image).text((10-bbox[0], 10-bbox[1]), text, font=face, fill="#ededed" if dark else "black")
    return image
