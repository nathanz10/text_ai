# Marketplace Car Ranker

Batch-extract and rank Facebook Marketplace car listings from screenshots using
Qwen 3 Vision through Ollama. The result is an Excel workbook sorted from the
best match to the weakest match according to the criteria in `src/car_ranker.py`.

## Project layout

```text
text-extractor/
├── data/
│   ├── calgary_awd_suvs_aug2026.csv  # Reference vehicle data
│   └── screenshots/                  # Marketplace screenshots
├── output/                           # Generated workbooks
├── src/
│   └── car_ranker.py                 # Extraction, scoring, and export script
├── requirements.txt
└── README.md
```

## Requirements

- macOS with Python 3.10 or newer
- Ollama
- A Mac mini or other Mac with enough memory for the selected model

The project was run locally on a Mac mini with Ollama serving the model. The
exact speed depends on the Mac mini chip, memory, image count, and model size.

## Configure Ollama and Qwen 3 Vision

Install Ollama from [ollama.com](https://ollama.com), then start the Ollama
application. In Terminal, download the model used by this project:

```bash
ollama pull qwen3-vl:8b
ollama list
```

`qwen3-vl:8b` is the vision-language version of Qwen 3 required for reading
the listing screenshots. The Python client connects to Ollama at its default
local address, `http://127.0.0.1:11434`.

To confirm the model works before running the batch job:

```bash
ollama run qwen3-vl:8b
```

Press `Ctrl-D` to leave the interactive prompt.

## Install the Python environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run the ranker

Make sure Ollama is running and the virtual environment is active, then run:

```bash
python src/car_ranker.py \
	--input data/screenshots \
	--output output/cars.xlsx
```

The script processes supported image files, extracts listing fields, applies
the ranking criteria in the source file, and writes the sorted workbook to
`output/cars.xlsx`. It also prints progress and the top three results.

To use another folder or output name:

```bash
python src/car_ranker.py --input path/to/screenshots --output output/results.xlsx
```

## Notes

- The model may return incomplete or incorrect fields; verify important details
	such as title status, mileage, price, and drivetrain against the original
	listing.
- Resized JPEGs may be created next to large source images while processing.
- Ranking thresholds and required drivetrain values are configured near the
	top of `src/car_ranker.py`.
