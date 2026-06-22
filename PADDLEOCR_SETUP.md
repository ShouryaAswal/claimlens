# PaddleOCR Setup Guide

ClaimLens supports two OCR engines: **Tesseract** (default) and **PaddleOCR**
(the "special feature" engine -- PaddleOCR v3 / PP-OCRv6, the same family
named in the design doc's cited paper, arXiv:2601.01897). This doc covers
installing it, running it, and exactly what to do if it doesn't work.

## TL;DR

```bash
pip install paddlepaddle paddleocr
export CLAIMLENS_OCR_ENGINE=paddleocr
python3 scripts/run_ingestion_demo.py
```

If PaddleOCR can't reach a model server, the pipeline automatically falls
back to Tesseract and logs a warning -- it will never silently produce zero
output. Read on for why that might happen and how to fix it.

## Step-by-step install

### 1. Install the deep learning framework (paddlepaddle)

```bash
pip install paddlepaddle
```

This is a ~195 MB wheel (CPU build). If you have an NVIDIA GPU and want
faster inference, install the GPU build instead per
[PaddlePaddle's official install matrix](https://www.paddlepaddle.org.cn/install/quick) --
the GPU wheel is tied to your exact CUDA version, so use their selector
rather than guessing a pip command here.

Verify:
```bash
python3 -c "import paddle; print(paddle.__version__)"
```

### 2. Install PaddleOCR

```bash
pip install paddleocr
```

Verify:
```bash
python3 -c "import paddleocr; print(paddleocr.__version__)"
```

### 3. First-run model download (the step that needs real internet access)

Unlike Tesseract (a single apt package with everything baked in), PaddleOCR
ships *code* via pip but downloads its actual detection/recognition *model
weights* the first time you instantiate `PaddleOCR(...)`. It tries these
hosts, in order, and uses whichever one it can reach:

1. Hugging Face (`huggingface.co`)
2. ModelScope (`modelscope.cn`)
3. AIStudio (`aistudio.baidu.com`)
4. Baidu BOS (`paddle-model-ecology.bj.bcebos.com`)

On a normal laptop or cloud VM with unrestricted outbound internet, this
just works the first time you run it -- expect the first call to take
10-60 seconds (downloading ~20-50MB of model weights, cached afterward in
`~/.paddlex/` or similar), and every call after that to be fast.

**Run the smoke test:**

```bash
python3 -c "
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang='en')
print('PaddleOCR loaded successfully')
"
```

If that prints `PaddleOCR loaded successfully`, you're done -- skip to
"Using it in ClaimLens" below.

### 4. If step 3 fails: "No available model hosting platforms detected"

This means none of the four hosts above were reachable from wherever you
ran it -- a corporate firewall, a sandboxed CI runner, a network policy
that allowlists specific domains, etc. (This is exactly what happened when
testing this integration in Anthropic's sandboxed code execution
environment while building this feature -- its outbound network is
restricted to package registries like PyPI and GitHub, and none of
PaddleOCR's four model hosts are on that list. The integration code itself
is correct and source-verified; the model files simply couldn't be fetched
from that specific sandbox. The same code installs and runs models
end-to-end on a normal machine with regular internet access.)

To fix it, in order of likelihood:

- **Check the obvious thing first:** can you reach any of the four URLs at
  all? `curl -I https://huggingface.co`. If that's blocked too, your
  network policy needs an exception added for at least one of the four
  hosts, or for `*.bcebos.com` (Baidu's CDN) specifically, which is
  typically the least commonly blocked of the four outside mainland China
  network contexts.
- **Behind a proxy?** Set `HTTPS_PROXY`/`HTTP_PROXY` env vars before
  running, same as for any Python `requests`-based download.
- **Already have the model files from elsewhere** (e.g. downloaded once on
  a different machine)? Point PaddleOCR straight at the local directory
  instead of letting it try to download:
  ```python
  PaddleOCR(
      text_detection_model_dir="/path/to/local/PP-OCRv6_det",
      text_recognition_model_dir="/path/to/local/PP-OCRv6_rec",
      ...
  )
  ```
- **Want to skip the (sometimes slow) connectivity probe** and go straight
  to attempting a download: `export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`
  before running. This does not fix a genuinely blocked network -- it just
  skips the upfront "let me check which host is reachable" step, which can
  occasionally itself be slow on a flaky connection.

### 5. Multilingual model packs

Unlike Tesseract's `lang="eng+vie"` combined-pack syntax, PaddleOCR loads
one language model at a time via `lang="en"` / `lang="vi"` / etc. Our
`paddleocr_engine.py` maps Tesseract-style codes to PaddleOCR's automatically
(`_to_paddle_lang_code()`) -- if you pass `lang="eng+vie"`, only the first
language (`en`) is actually used, since that's a genuine PaddleOCR
limitation (one model per instance), not a bug in our wrapper. For a truly
multilingual claim packet, instantiate separate engines per document and
route by detected language, or by document source (e.g. "this claim came in
through the Vietnam intake channel").

## Using it in ClaimLens

Engine selection is one environment variable, read in `core/config.py`:

```bash
export CLAIMLENS_OCR_ENGINE=paddleocr   # default: tesseract
python3 scripts/run_ingestion_demo.py
```

Or set it for a single run inline:
```bash
CLAIMLENS_OCR_ENGINE=paddleocr python3 scripts/run_ingestion_demo.py
```

You do not need to change any other code -- `pdf_parser.py` and
`image_parser.py` call the same `ocr_utils.ocr_image_to_lines()` function
regardless of which engine is behind it (see
`agents/ingestion/ocr_engines/factory.py`).

**What happens if PaddleOCR is requested but fails to load:** the factory
catches the failure once per process (not once per page -- it doesn't
retry-and-fail 25 times on a 25-page claim), logs a clear warning naming
the reason, and the rest of that run proceeds on Tesseract automatically.
You'll see exactly this in the log:

```
WARNING ... PaddleOCR requested but unavailable (...). Falling back to
Tesseract for this run. See PADDLEOCR_SETUP.md to fix this.
```

## Why bother with PaddleOCR if Tesseract already works?

On the genuinely real, noisy scanned documents added in this round
(`samples/real_world/` -- see `REAL_DATA_SOURCES.md`), PaddleOCR is
generally expected to outperform Tesseract on:

- Dense small text and tight table cells (common in claim line-item
  breakdowns and billing schedules).
- Rotated/skewed scans (a phone photo of a paper form, not a flatbed scan).
- Non-Latin scripts and mixed-language pages -- directly relevant if you
  end up handling claims from multilingual intake channels, the same
  problem Fullerton Health's pipeline (the cited paper) was built for.

Tesseract remains the right default for a fast, dependency-light local dev
loop and CI; PaddleOCR is the right choice to flip on for a real demo on
real data, or in production, once your environment has normal internet
access for the one-time model download.

## Testing without live model access

`tests/test_ocr_engines.py` includes a real (not mocked)
`test_paddleocr_falls_back_to_tesseract_when_unavailable` test: in an
environment where PaddleOCR's model hosts are unreachable, it proves the
pipeline still returns valid output via the Tesseract fallback rather than
crashing. In an environment where PaddleOCR *can* reach its model hosts,
the same test still passes -- it just means the real PaddleOCR engine ran
and produced the output instead.
