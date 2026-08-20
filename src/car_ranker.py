"""
Batch extraction + ranking for Facebook Marketplace car listing screenshots.

Reads every screenshot in an input folder, extracts structured car listing
fields using Qwen3-VL via Ollama, scores each listing against your criteria,
and writes everything to an .xlsx sorted best-to-worst.

Usage:
    python src/car_ranker.py --input data/screenshots --output output/cars.xlsx
"""

import argparse
import json
import re
from pathlib import Path

import ollama
from openpyxl import Workbook
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

MODEL = "qwen3-vl:8b"
NUM_CTX = 16384

PROMPT = """This is a screenshot of a Facebook Marketplace car listing. Extract the following fields as JSON:

- year (integer or null)
- make (string or null)
- model (string or null)
- trim (string or null)
- price (number, CAD, no currency symbol, or null)
- mileage_km (number, convert from miles if needed, or null)
- title_status ("clean", "rebuilt", "salvage", "active", or null if not stated)
- drivetrain ("AWD", "4WD", "FWD", "RWD", or null)
- location (city/region, or null)
- seller_type ("private", "dealer", or null)
- winter_tires_mentioned (true/false)
- condition_notes (short string summarizing any damage, issues, or notable condition details mentioned)
- listing_description (the raw description text as it appears)

Output only valid JSON, nothing else. Use null for any field not clearly stated in the listing."""

FIELDS = [
    "filename", "score", "year", "make", "model", "trim", "price", "mileage_km",
    "title_status", "drivetrain", "location", "seller_type",
    "winter_tires_mentioned", "condition_notes", "listing_description",
]

# --- Your ranking criteria (from car-purchase-red-deer plan) ---
BUDGET_MIN = 8000
BUDGET_MAX = 13000
BUDGET_SWEET_SPOT = 11000  # scores highest near here
MAX_MILEAGE_KM = 180000
GOOD_MILEAGE_KM = 120000
REQUIRED_DRIVETRAIN = {"AWD", "4WD"}


def resize_if_needed(path: Path, max_dim: int = 1600) -> Path:
    with Image.open(path) as img:
        img = img.convert("RGB")
        if max(img.size) <= max_dim:
            if path.suffix.lower() != ".heic":
                return path
            out = path.with_suffix(".jpg")
            img.save(out)
            return out
        img.thumbnail((max_dim, max_dim))
        out = path.with_stem(path.stem + "_resized").with_suffix(".jpg")
        img.save(out)
        return out


def extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def score_listing(data: dict) -> tuple[int, list[str]]:
    """Score 0-100. Returns (score, reasons) so you can see why."""
    score = 0
    reasons = []

    # Title status - hard filter territory
    status = (data.get("title_status") or "").lower()
    if status == "rebuilt" or status == "salvage":
        return 0, [f"Disqualified: title status is '{status}'"]
    elif status == "clean" or status == "active":
        score += 25
        reasons.append("Clean/active title (+25)")
    else:
        score += 10
        reasons.append("Title status unknown, unverified (+10)")

    # Drivetrain - required
    drivetrain = (data.get("drivetrain") or "").upper()
    if drivetrain in REQUIRED_DRIVETRAIN:
        score += 20
        reasons.append(f"{drivetrain} drivetrain (+20)")
    else:
        reasons.append("Not AWD/4WD (0) — check listing manually")

    # Price - sweet spot scoring
    price = data.get("price")
    if price:
        if BUDGET_MIN <= price <= BUDGET_MAX:
            distance = abs(price - BUDGET_SWEET_SPOT)
            price_score = max(0, 20 - int(distance / 250))
            score += price_score
            reasons.append(f"Price ${price} in budget (+{price_score})")
        elif price < BUDGET_MIN:
            score += 15
            reasons.append(f"Price ${price} below budget — good value, verify condition (+15)")
        else:
            reasons.append(f"Price ${price} over budget (0)")

    # Mileage
    mileage = data.get("mileage_km")
    if mileage:
        if mileage <= GOOD_MILEAGE_KM:
            score += 20
            reasons.append(f"{mileage}km — low mileage (+20)")
        elif mileage <= MAX_MILEAGE_KM:
            score += 10
            reasons.append(f"{mileage}km — acceptable (+10)")
        else:
            reasons.append(f"{mileage}km — high mileage (0)")

    # Winter tires
    if data.get("winter_tires_mentioned"):
        score += 10
        reasons.append("Winter tires included (+10)")

    # Seller type - private slightly preferred for price flexibility
    if (data.get("seller_type") or "").lower() == "private":
        score += 5
        reasons.append("Private seller (+5)")

    return min(score, 100), reasons


def process_image(path: Path) -> dict:
    working_path = resize_if_needed(path)
    response = ollama.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": PROMPT,
            "images": [str(working_path)],
        }],
        options={"num_ctx": NUM_CTX},
    )
    raw = response["message"]["content"]
    parsed = extract_json(raw)

    row = {"filename": path.name}
    if parsed:
        score, reasons = score_listing(parsed)
        row["score"] = score
        for f in FIELDS:
            if f not in ("filename", "score"):
                row[f] = parsed.get(f)
        row["_reasons"] = "; ".join(reasons)
    else:
        row["score"] = None
        row["_reasons"] = "Failed to parse JSON from model output"
        for f in FIELDS:
            if f not in ("filename", "score"):
                row[f] = None

    return row


def main():
    parser = argparse.ArgumentParser(description="Rank Marketplace car listings from screenshots")
    parser.add_argument("--input", required=True, help="Folder of screenshots")
    parser.add_argument("--output", default="output/cars.xlsx", help="Output .xlsx path")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".heic")
    )

    if not image_paths:
        print(f"No images found in {input_dir}")
        return

    results = []
    for i, img_path in enumerate(image_paths, 1):
        print(f"[{i}/{len(image_paths)}] Processing {img_path.name}...")
        try:
            row = process_image(img_path)
            results.append(row)
            print(f"  -> score: {row['score']}")
        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append({"filename": img_path.name, "score": None, "_reasons": f"Error: {e}",
                             **{f: None for f in FIELDS if f not in ("filename", "score")}})

    # Sort best to worst, unscored/failed listings at the bottom
    results.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))

    wb = Workbook()
    ws = wb.active
    ws.title = "car_rankings"
    ws.append(FIELDS + ["notes_why_this_score"])
    for row in results:
        ws.append([row.get(f) for f in FIELDS] + [row.get("_reasons")])
    wb.save(output_path)

    print(f"\nDone. Ranked {len(results)} listings -> {output_path}")
    top = [r for r in results if r["score"]][:3]
    if top:
        print("\nTop 3:")
        for r in top:
            print(f"  {r['score']:>3} | {r.get('year')} {r.get('make')} {r.get('model')} - ${r.get('price')} - {r.get('mileage_km')}km - {r['filename']}")


if __name__ == "__main__":
    main()
