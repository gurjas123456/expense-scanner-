"""
EasyOCR-based receipt processing service — Production Ready.

Improvements over base version:
- Robust noise suppression: ZIP codes, phone numbers (intl/domestic), dates,
  times, GST/HSN codes, barcodes, UPI IDs, email addresses, URLs, order/invoice
  IDs, loyalty card numbers, and alphanumeric product SKUs are all stripped
  before amount extraction to prevent false positives.
- Defensive amount parsing with strict range and format guards.
- Structured logging instead of bare print().
- Full type annotations and docstrings.
- Thread-safe lazy EasyOCR initialization.
- Graceful degradation with clear error taxonomy.
"""

from __future__ import annotations

import importlib
import logging
import os
import pickle
import re
import threading
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compiled noise patterns (compiled once at module load for performance)
# ---------------------------------------------------------------------------

# ── Phone numbers ────────────────────────────────────────────────────────────
# Covers:  +91-98765-43210  |  (800) 555-1234  |  1-800-555-1234
#          91 9876543210    |  +1 800 555 1234  |  040-23456789 (landline)
#
# Fix: require at least 7 contiguous digit characters total (via the two
# mandatory digit groups) so short prices like "234.50" don't match.
# Also anchored with (?<!\d) / (?!\d) to avoid mid-number fires.
_RE_PHONE = re.compile(
    r"""
    (?<!\d)
    (?:
        (?:\+?\d{1,3}[\s\-.])?          # optional country code
        (?:\(?\d{2,5}\)?[\s\-.])?       # optional area/STD code
        \d{4,5}                          # first digit group  ← min 4 digits
        [\s\-.]                          # separator (required)
        \d{4,5}                          # second digit group ← min 4 digits
        (?:[\s\-.]\d{2,5})?             # optional third group
    )
    (?!\d)
    """,
    re.VERBOSE,
)

# ── ZIP / PIN codes ──────────────────────────────────────────────────────────
# US ZIP: 12345 or 12345-6789
# UK postcode: SW1A 1AA
# Canadian: A1A 1A1
#
# Fix: `\d{5}` must NOT be followed by `.` (which would make it a price like
# 12345.67) and must not be preceded by one either.
_RE_ZIP = re.compile(
    r"""
    (?<!\d)
    (?:
        \d{5}(?:-\d{4})?(?!\.)            # US ZIP — not followed by decimal point
        | [A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}  # UK postcode
        | [A-Z]\d[A-Z]\s*\d[A-Z]\d        # Canadian postal code
    )
    (?!\d)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Indian PIN (6 digits) is caught by the long-number rule (≥5 digits); 
# kept separate for clarity and labelled context removal.
_RE_INDIAN_PIN = re.compile(
    r"\b(?:PIN|Pincode|Zip)[:\s]*\d{6}\b", re.IGNORECASE
)

# ── Dates ────────────────────────────────────────────────────────────────────
_RE_DATE = re.compile(
    r"""
    \b
    (?:
        \d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}  # DD/MM/YY or MM-DD-YYYY etc.
        | \d{4}[/\-\.]\d{2}[/\-\.]\d{2}       # ISO: YYYY-MM-DD
        | \d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}
    )
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ── Times ────────────────────────────────────────────────────────────────────
_RE_TIME = re.compile(
    r"\b(?:\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?|\d{1,2}\.\d{2}(?:\.\d{2})?\s*[AaPp][Mm]?)\b"
)

# ── URLs / websites ──────────────────────────────────────────────────────────
_RE_URL = re.compile(
    r"(?:https?://|www\.)\S+", re.IGNORECASE
)

# ── Email addresses ──────────────────────────────────────────────────────────
_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# ── UPI IDs (India) ──────────────────────────────────────────────────────────
_RE_UPI = re.compile(
    r"\b[A-Za-z0-9.\-_]+@[a-z]{3,10}\b"  # e.g. merchant@okaxis
)

# ── GST / GSTIN (India, 15-char alphanumeric) ────────────────────────────────
_RE_GSTIN = re.compile(
    r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b"
)

# ── HSN / SAC codes ──────────────────────────────────────────────────────────
_RE_HSN = re.compile(
    r"\bHSN[:\s]*\d{4,8}\b|\bSAC[:\s]*\d{4,6}\b", re.IGNORECASE
)

# ── Barcodes / long pure-digit strings ───────────────────────────────────────
# Keep 4-digit and shorter (could be qty/year); remove 5+ digit standalone nums
_RE_LONG_NUMBER = re.compile(r"\b\d{5,}\b(?![.,]\d{1,2}\b)")

# ── Long alphanumeric codes (product SKUs, serial numbers, tokens) ────────────
# Fix: must contain at least one digit — pure UPPERCASE words like TOTAL,
# GRAND, AMOUNT are label keywords we need intact, so don't strip them.
_RE_ALPHANUM_CODE = re.compile(r"\b(?=[A-Z0-9]{8,}\b)(?=[A-Z]*\d)[A-Z0-9]{8,}\b")

# ── Order / Invoice / Receipt identifiers ────────────────────────────────────
_RE_ORDER_ID = re.compile(
    r"\b(?:Order|Inv(?:oice)?|Receipt|Bill|Ticket|Ref|Trans(?:action)?)"
    r"[:\s#]*[A-Z0-9\-/]{4,}\b",
    re.IGNORECASE,
)

# ── Loyalty / membership card numbers ────────────────────────────────────────
_RE_LOYALTY = re.compile(
    r"\b(?:Card|Member|Customer|Loyalty|Reward)[:\s#]*[A-Z0-9\-]{6,}\b",
    re.IGNORECASE,
)

# ── OCR currency symbol mis-reads ────────────────────────────────────────────
# S$ → space, stray $ / ₹ / £ / € before digits
_RE_CURRENCY_PREFIX = re.compile(r"[S$s]\s*(\d+\.\d{2})")

# ── Amount token pattern (used after noise removal) ──────────────────────────
# Matches numbers like: 1234  1,234  1,234.56  1234.5
#
# Fixes vs original:
# - Lookbehind/ahead now blocks [A-Za-z0-9] (was only [a-z0-9]) so "ABC123"
#   and "Rs123" don't bleed through.
# - Negative lookbehind also excludes "." and "-" so decimals mid-number and
#   negative/hyphenated tokens are not double-matched.
# - Decimal part requires exactly 1-2 digits (not 0) to avoid bare "1234."
_AMOUNT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.\-])\d[\d,]*(?:\.\d{1,2})?(?![A-Za-z0-9])"
)

# ── Noise patterns that precede phone/mobile numbers ────────────────────────
_RE_PHONE_LABEL = re.compile(
    r"(?:Ph(?:one)?|Mob(?:ile)?|Tel(?:ephone)?|Fax|Contact|Call)[:\s=;(]*[\d\s\-+().]{7,20}",
    re.IGNORECASE,
)

# ── Tax rate percentages that look like amounts (e.g. "18%", "5 %") ──────────
_RE_PERCENTAGE = re.compile(r"\b\d{1,3}\s*%")

# ── Table/column headers with numbers (e.g. "Qty 2", "Sl.No 1") ─────────────
_RE_QTY_LABEL = re.compile(
    r"\b(?:Qty|Quantity|Sl\.?No\.?|S\.?No\.?|Sr\.?No\.?|Item\s*No\.?)[:\s]*\d+",
    re.IGNORECASE,
)

# ── Discount/offer codes (e.g. SAVE10, OFF20) ────────────────────────────────
_RE_PROMO_CODE = re.compile(r"\b(?:SAVE|OFF|DISC|COUPON|PROMO)\d+\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_noise(text: str) -> str:
    """
    Remove all non-amount numeric noise from raw OCR text.

    Order matters: remove labelled patterns first (more specific),
    then bare patterns (broader).
    """
    # Fix currency mis-reads early so later steps see clean numbers
    text = _RE_CURRENCY_PREFIX.sub(r" \1", text)

    # Labelled removals (phone label, order ID, loyalty card, UPI, HSN)
    text = _RE_PHONE_LABEL.sub(" ", text)
    text = _RE_ORDER_ID.sub(" ", text)
    text = _RE_LOYALTY.sub(" ", text)
    text = _RE_GSTIN.sub(" ", text)
    text = _RE_HSN.sub(" ", text)
    text = _RE_INDIAN_PIN.sub(" ", text)

    # Structured patterns
    text = _RE_URL.sub(" ", text)
    text = _RE_EMAIL.sub(" ", text)
    text = _RE_UPI.sub(" ", text)
    text = _RE_DATE.sub(" ", text)
    text = _RE_TIME.sub(" ", text)
    text = _RE_ZIP.sub(" ", text)
    text = _RE_PERCENTAGE.sub(" ", text)
    text = _RE_QTY_LABEL.sub(" ", text)
    text = _RE_PROMO_CODE.sub(" ", text)

    # Broad catch-alls last (after specific patterns are gone)
    text = _RE_PHONE.sub(" ", text)          # bare phone numbers
    text = _RE_LONG_NUMBER.sub(" ", text)    # 5+ digit standalone numbers
    text = _RE_ALPHANUM_CODE.sub(" ", text)  # SKUs / serials

    # Normalize whitespace while preserving line structure for amount heuristics.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    return text.strip()


def _parse_amount_token(token: str) -> Optional[float]:
    """
    Parse a single numeric token into a float bill amount.

    Handles:
    - Plain integers:            1234
    - Thousands separator:       1,234
    - Decimal:                   1234.56
    - Indian lakh format:        1,23,456.00
    - European comma-decimal:    1234,56  → 1234.56

    Returns None for values outside (0, 1_000_000] or unparseable tokens.
    """
    token = str(token).strip().strip(",.")
    if not token:
        return None

    # Remove internal whitespace (OCR sometimes splits "1 234.56")
    token = re.sub(r"\s+", "", token)

    if "." in token:
        # Decimal present — commas are thousands separators
        normalized = token.replace(",", "")
    elif token.count(",") >= 2:
        # Multiple commas → Indian / European thousands notation
        parts = [p for p in token.split(",") if p]
        if not parts:
            return None
        # If last segment is ≤2 digits, treat as decimal cents
        if len(parts[-1]) <= 2:
            normalized = "".join(parts[:-1]) + "." + parts[-1]
        else:
            normalized = "".join(parts)
    elif "," in token:
        left, right = token.split(",", 1)
        # Single comma: European decimal if right side is 1-2 digits
        if len(right) in {1, 2}:
            normalized = left + "." + right
        else:
            normalized = left + right
    else:
        normalized = token

    try:
        value = float(normalized)
    except ValueError:
        return None

    # Tightened range: ₹1.00 – ₹1,00,000 (sub-rupee and crore-level are noise)
    # Adjust _MAX_BILL_AMOUNT if your domain requires higher (e.g. B2B invoices).
    _MIN_BILL_AMOUNT = 1.0
    _MAX_BILL_AMOUNT = 100_000.0
    if _MIN_BILL_AMOUNT <= value <= _MAX_BILL_AMOUNT:
        return round(value, 2)
    return None


# ---------------------------------------------------------------------------
# OCRService
# ---------------------------------------------------------------------------

class OCRService:
    """
    Receipt OCR service backed by EasyOCR for text extraction.

    Provides:
    - Preprocessing and OCR via EasyOCR
    - ML-based expense category classification
    - Robust bill-amount extraction with comprehensive noise filtering
    - Optional plug-in of an end-to-end receipt model
    """

    def __init__(
        self,
        models_dir: Optional[str] = None,
        use_gpu: bool = False,
        ocr_backend: str = "easyocr",
    ) -> None:
        """
        Initialise OCRService.

        Args:
            models_dir: Directory containing model.pkl, vectorizer.pkl, encoder.pkl.
                        Defaults to the directory of this source file.
            use_gpu:    Whether to use GPU acceleration for EasyOCR.
            ocr_backend: OCR backend identifier (currently only "easyocr").
        """
        if models_dir is None:
            models_dir = os.path.dirname(os.path.abspath(__file__))

        self.models_dir = models_dir
        self.use_gpu = use_gpu
        self.ocr_backend = ocr_backend or "easyocr"
        self.loaded_backend = "easyocr"

        # ML model components
        self.model = None
        self.vectorizer = None
        self.encoder = None

        # OCR — lazily initialised; guarded by a lock for thread safety
        self._easy_reader: Optional[object] = None
        self._easy_reader_lock = threading.Lock()

        # Optional end-to-end receipt model
        self.receipt_model = None
        self.receipt_model_name: Optional[str] = None

        # Feature flag: allow falling back to legacy pipeline
        self.allow_legacy_fallback: bool = os.getenv(
            "ALLOW_LEGACY_FALLBACK", ""
        ).strip().lower() in {"1", "true", "yes", "on"}

        # Load models
        self._load_receipt_model()
        if self.receipt_model is None or self.allow_legacy_fallback:
            self._load_models()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        """Load trained ML model, vectorizer, and encoder from pickle files."""
        paths = {
            "model": os.path.join(self.models_dir, "model.pkl"),
            "vectorizer": os.path.join(self.models_dir, "vectorizer.pkl"),
            "encoder": os.path.join(self.models_dir, "encoder.pkl"),
        }

        for name, path in paths.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"{name} file not found: {path}")

        try:
            with open(paths["model"], "rb") as fh:
                self.model = pickle.load(fh)
            with open(paths["vectorizer"], "rb") as fh:
                self.vectorizer = pickle.load(fh)
            with open(paths["encoder"], "rb") as fh:
                self.encoder = pickle.load(fh)
        except Exception as exc:
            raise RuntimeError(f"Failed to load model files: {exc}") from exc

        logger.info("ML models loaded from %s", self.models_dir)

    def _ensure_easyocr(self) -> None:
        """Thread-safe lazy initialisation of EasyOCR reader."""
        if self._easy_reader is not None:
            return

        with self._easy_reader_lock:
            if self._easy_reader is not None:   # double-checked locking
                return
            try:
                import easyocr  # noqa: PLC0415
            except ImportError as exc:
                raise ImportError(
                    "EasyOCR is not installed. Install with: pip install easyocr"
                ) from exc
            try:
                self._easy_reader = easyocr.Reader(["en"], gpu=self.use_gpu)
                logger.info("EasyOCR reader initialised (gpu=%s)", self.use_gpu)
            except Exception as exc:
                raise RuntimeError(f"Failed to initialise EasyOCR: {exc}") from exc

    def _load_receipt_model(self) -> None:
        """Load an optional end-to-end receipt model adapter via env vars."""
        module_name = os.getenv("RECEIPT_MODEL_MODULE")
        class_name = os.getenv("RECEIPT_MODEL_CLASS", "ReceiptModel")

        if not module_name:
            return

        try:
            module = importlib.import_module(module_name)
            model_cls = getattr(module, class_name)
            self.receipt_model = model_cls(
                models_dir=self.models_dir,
                use_gpu=self.use_gpu,
                backend_name=self.ocr_backend,
            )
            self.receipt_model_name = module_name
            logger.info("Receipt model loaded: %s.%s", module_name, class_name)
        except Exception as exc:
            logger.warning("Failed to load receipt model '%s': %s", module_name, exc)

    # ------------------------------------------------------------------
    # Receipt-model adapter helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_model_payload(result: Union[Dict, object]) -> Dict:
        """Normalise result objects from different custom model styles."""
        if isinstance(result, dict):
            return result
        if hasattr(result, "to_dict"):
            payload = result.to_dict()
            if isinstance(payload, dict):
                return payload
        raise TypeError(
            "Receipt model must return a dict or an object with to_dict()."
        )

    def _predict_with_receipt_model(self, image_path: str) -> Optional[Dict]:
        """
        Run the configured end-to-end model and normalise its output.

        Raises:
            AttributeError: If model doesn't expose a recognised inference method.
            KeyError: If 'amount' field is missing from result.
            ValueError: If model returns None.
        """
        if self.receipt_model is None:
            return None

        # Try recognised inference method names in priority order
        payload: Optional[Dict] = None
        for fn_name in ("process_receipt", "predict", "infer"):
            fn = getattr(self.receipt_model, fn_name, None)
            if callable(fn):
                payload = self._extract_model_payload(fn(image_path))
                break
        else:
            if callable(self.receipt_model):
                payload = self._extract_model_payload(self.receipt_model(image_path))
            else:
                raise AttributeError(
                    "Receipt model must expose process_receipt(), predict(), infer(), "
                    "or be callable."
                )

        if payload is None:
            raise ValueError("Receipt model returned None.")

        if "amount" not in payload:
            raise KeyError("Receipt model output must include an 'amount' field.")

        amount = float(payload["amount"])
        all_amounts = [float(v) for v in payload.get("all_amounts", [amount])]
        category = payload.get("category", "Others")
        raw_text = payload.get("raw_text", "")
        cleaned_text = payload.get(
            "cleaned_text", self.clean_text(raw_text) if raw_text else ""
        )

        return {
            "category": category,
            "amount": amount,
            "all_amounts": sorted(set(all_amounts), reverse=True),
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "ocr_backend": payload.get("ocr_backend", self.ocr_backend),
        }

    # ------------------------------------------------------------------
    # Image processing & OCR
    # ------------------------------------------------------------------

    @staticmethod
    def preprocess_image(image_path: str) -> np.ndarray:
        """
        Preprocess a receipt image for better OCR accuracy.

        Steps: load → upscale → grayscale → sharpen.

        Raises:
            FileNotFoundError: If the image cannot be loaded by OpenCV.
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Could not load image: {image_path}")

        img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        return cv2.filter2D(gray, -1, kernel)

    def extract_text(self, image_path: str) -> str:
        """
        Extract text from a receipt image using EasyOCR.

        Args:
            image_path: Path to the receipt image.

        Returns:
            Concatenated OCR text.
        """
        self._ensure_easyocr()
        processed = self.preprocess_image(image_path)
        results = self._easy_reader.readtext(processed)
        self.loaded_backend = "easyocr"
        if not results:
            return ""

        tokens = []
        heights = []
        for box, text, _confidence in results:
            if not text or not str(text).strip():
                continue

            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            token = {
                "text": str(text).strip(),
                "x": sum(xs) / len(xs),
                "y": sum(ys) / len(ys),
                "height": max(ys) - min(ys),
            }
            tokens.append(token)
            heights.append(token["height"])

        if not tokens:
            return ""

        sorted_heights = sorted(heights)
        median_height = sorted_heights[len(sorted_heights) // 2]
        line_threshold = max(25.0, median_height * 0.65)

        tokens.sort(key=lambda token: (token["y"], token["x"]))
        lines = []
        for token in tokens:
            for line in lines:
                if abs(token["y"] - line["y"]) <= line_threshold:
                    line["tokens"].append(token)
                    line["y"] = sum(item["y"] for item in line["tokens"]) / len(line["tokens"])
                    break
            else:
                lines.append({"y": token["y"], "tokens": [token]})

        ordered_lines = []
        for line in sorted(lines, key=lambda item: item["y"]):
            line["tokens"].sort(key=lambda token: token["x"])
            ordered_lines.append(" ".join(token["text"] for token in line["tokens"]))

        return "\n".join(ordered_lines)

    # ------------------------------------------------------------------
    # Text cleaning & classification
    # ------------------------------------------------------------------

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Clean raw OCR text for ML model input.

        Strips digits, currency symbols, punctuation, and normalises whitespace.
        """
        text = text.lower()
        text = re.sub(r"\d+", "", text)
        text = re.sub(r"rs", "", text)
        text = re.sub(r"[^a-z\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def predict_category(self, text: str) -> str:
        """
        Predict expense category from cleaned text.

        Tries keyword matching first (fast path), then falls back to the ML model.

        Args:
            text: Cleaned (lowercased, no-digits) receipt text.

        Returns:
            Category string.
        """
        if self.model is None or self.vectorizer is None or self.encoder is None:
            return "Others"

        text_lower = text.lower()

        food_kw = {
            "restaurant", "hotel", "pizzeria", "cafe", "diner", "eatery", "food",
            "dining", "menu", "order", "meal", "breakfast", "lunch", "dinner",
            "snack", "cuisine", "pizza", "burger", "coffee", "pasta", "sandwich",
            "dominos", "kfc", "biryani", "noodles", "tea", "zomato", "swiggy",
            "dine", "hungry", "cheese", "roast", "chicken", "chickan", "lamb",
            "risotto", "soup", "wine", "beer", "drink", "bakery", "paneer",
            "dal", "rice", "roti", "naan", "kebab", "grill",
        }
        healthcare_kw = {
            "doctor", "hospital", "clinic", "medical", "surgery", "pharmacy",
            "medicine", "prescription", "vaccine", "vaccination", "treatment",
            "therapy", "patient", "veterinary", "veterinarian", "disease",
            "illness", "infection", "fever", "health", "dental", "orthopedic",
            "cardiology", "neurology",
        }
        groceries_kw = {
            "grocery", "supermarket", "market", "fruit", "vegetable", "store",
            "big basket", "blinkit", "dmart", "lulu", "costco",
        }
        shopping_kw = {
            "amazon", "flipkart", "myntra", "h&m", "zara", "uniqlo", "mall",
            "departm", "retail", "clothing", "apparel", "fashion", "shoe",
        }

        words = set(text_lower.split())
        if words & food_kw or any(kw in text_lower for kw in food_kw):
            return "Food"
        if words & healthcare_kw or any(kw in text_lower for kw in healthcare_kw):
            return "Healthcare"
        if words & groceries_kw or any(kw in text_lower for kw in groceries_kw):
            return "Groceries"
        if words & shopping_kw or any(kw in text_lower for kw in shopping_kw):
            return "Shopping"

        try:
            x_val = self.vectorizer.transform([text])
            return self.encoder.inverse_transform(self.model.predict(x_val))[0]
        except Exception as exc:
            logger.warning("ML prediction error: %s", exc)
            return "Others"

    def refine_category(self, raw_text: str, category: str) -> str:
        """
        Apply strong receipt-text heuristics after ML prediction.

        Args:
            raw_text: Original OCR text.
            category: Category returned by predict_category().

        Returns:
            Final, refined category.
        """
        text = (raw_text or "").lower()

        food_signals = {"dominos", "domino's", "pizza", "burger", "mojito", "risotto", "restaurant"}
        healthcare_signals = {"pharmacy", "medicine", "clinic", "veterinary", "doctor", "hospital"}
        grocery_signals = {"trader joe", "grocery", "supermarket"}
        shopping_signals = {"walmart", "superstore", "t-shirt", "push pins"}

        if any(kw in text for kw in food_signals):
            return "Food"
        if any(kw in text for kw in healthcare_signals):
            return "Healthcare"
        if any(kw in text for kw in grocery_signals):
            return "Groceries"
        if any(kw in text for kw in shopping_signals):
            return "Shopping"

        return category

    # ------------------------------------------------------------------
    # Amount extraction  (production-hardened)
    # ------------------------------------------------------------------

    @staticmethod
    def extract_bill_amount(raw_text: str) -> Tuple[List[float], float]:
        """
        Extract the most likely total amount from OCR receipt text.

        Algorithm:
        1. Strip all non-amount noise (phones, ZIPs, dates, IDs, …).
        2. Collect all remaining candidate amounts.
        3. Score candidates using three independent strategies:
           a. Explicit label matching  (highest confidence)
           b. Position in document     (totals appear near end)
           c. Line-structure analysis  (last value on last lines)
        4. Rank by score; return best candidate and full amount list.

        Args:
            raw_text: Raw OCR text from the receipt.

        Returns:
            (all_amounts, best_amount) — all_amounts is sorted descending.
        """
        if not raw_text or not raw_text.strip():
            return [], 0.0

        # ── Step 1: Remove noise ───────────────────────────────────────────
        cleaned = _strip_noise(raw_text)

        # ── Step 2: Collect all candidate amounts ─────────────────────────
        all_amounts: List[float] = []
        for m in _AMOUNT_PATTERN.finditer(cleaned):
            val = _parse_amount_token(m.group(0))
            if val is not None:
                all_amounts.append(val)
        all_amounts = sorted(set(all_amounts), reverse=True)
        value_counts: Dict[float, int] = {}
        for m in _AMOUNT_PATTERN.finditer(cleaned):
            val = _parse_amount_token(m.group(0))
            if val is not None:
                value_counts[val] = value_counts.get(val, 0) + 1

        if not all_amounts:
            return [], 0.0

        # ── Step 3a: Explicit total-label strategy ────────────────────────
        def _label_candidates(text: str) -> List[Tuple[int, float]]:
            total_labels = [
                (r"bill\s+total[:\s]+",      10),
                (r"grand\s+total[:\s]+",     10),
                (r"net\s+total[:\s]+",       10),
                (r"invoice\s+total[:\s]+",   10),
                (r"total\s+amount[:\s]+",    10),
                (r"amount\s+due[:\s]+",       9),
                (r"to\s+pay[:\s]+",           9),
                (r"payable[:\s]+",            9),
                (r"\btotal\b[:\s]+",          8),
                (r"amount[:\s]+(?!of)",       7),
            ]
            scored: List[Tuple[int, float]] = []
            skip_prefixes = {"sub", "cgst", "sgst", "igst", "vat", "tax", "service"}

            for pattern, confidence in total_labels:
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    after = text[m.end(): m.end() + 30]
                    hits = _AMOUNT_PATTERN.findall(after)
                    if not hits:
                        continue
                    val = _parse_amount_token(hits[0])
                    if val is None:
                        continue
                    prefix = text[max(0, m.start() - 30): m.start()].lower()
                    adj_conf = confidence - 3 if any(p in prefix for p in skip_prefixes) else confidence
                    if adj_conf > 0:
                        scored.append((adj_conf, val))

            return scored

        # ── Step 3b: Position-based strategy ─────────────────────────────
        def _position_candidates(text: str) -> List[Tuple[int, float]]:
            scored: List[Tuple[int, float]] = []
            length = len(text)
            for m in _AMOUNT_PATTERN.finditer(text):
                val = _parse_amount_token(m.group(0))
                if val is None:
                    continue
                ratio = m.start() / length if length else 0
                if ratio > 0.80:
                    conf = 7
                elif ratio > 0.60:
                    conf = 5
                else:
                    conf = 2
                context_before = text[max(0, m.start() - 24): m.start()].lower()
                context_after = text[m.end(): m.end() + 16].lower()
                nearby = f"{context_before} {context_after}"
                if re.search(r"\b(?:mg|ml|g|kg|lb|lbs|oz|qty|weight)\b", nearby):
                    conf -= 6
                if any(keyword in nearby for keyword in ("charge", "payment", "paid", "balance", "net price", "amount", "total")):
                    conf += 4
                if any(keyword in nearby for keyword in ("change", "cash", "tender", "credit tend", "debit", "refund")):
                    conf -= 8
                scored.append((conf, val))
            return scored

        # ── Step 3c: Line-structure strategy ─────────────────────────────
        def _line_candidates(text: str) -> List[Tuple[int, float]]:
            scored: List[Tuple[int, float]] = []
            lines = text.splitlines()
            window_start = max(0, len(lines) - 5)
            for idx in range(window_start, len(lines)):
                lower_line = lines[idx].lower()
                line_vals: List[float] = []
                for m in _AMOUNT_PATTERN.finditer(lines[idx]):
                    val = _parse_amount_token(m.group(0))
                    if val is not None:
                        line_vals.append(val)
                if line_vals:
                    # Last value on later lines gets higher score
                    score = 6 + (idx - window_start)
                    if any(keyword in lower_line for keyword in ("charge", "payment", "amount", "total", "balance", "net price")):
                        score += 4
                    if any(keyword in lower_line for keyword in ("change", "cash", "tender", "credit tend", "debit", "refund")):
                        score -= 8
                    selected_value = line_vals[-1]
                    if any(keyword in lower_line for keyword in ("charge", "payment", "balance", "net price", "description")):
                        selected_value = max(line_vals)
                    scored.append((score, selected_value))
            return scored

        def _frequency_candidates() -> List[Tuple[int, float]]:
            scored: List[Tuple[int, float]] = []
            for value, count in value_counts.items():
                if count > 1:
                    scored.append((4 + min(count, 3), value))
            return scored

        # ── Step 4: Combine and rank ──────────────────────────────────────
        candidates = (
            _label_candidates(cleaned)
            + _position_candidates(cleaned)
            + _line_candidates(cleaned)
            + _frequency_candidates()
        )

        if not candidates:
            # Ultimate fallback: largest detected amount
            return all_amounts, all_amounts[0] if all_amounts else 0.0

        # Sort by score desc, then amount desc (to break ties favouring larger totals)
        candidates.sort(key=lambda x: (-x[0], -x[1]))
        best_total = round(candidates[0][1], 2)

        # Ensure best_total appears in the return list
        unique = sorted(set(all_amounts), reverse=True)
        if best_total not in unique and best_total > 0:
            unique.insert(0, best_total)

        return unique, best_total

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_receipt(self, image_path: str) -> Dict:
        """
        Run the full OCR → classify → extract pipeline on a receipt image.

        Args:
            image_path: Filesystem path to the receipt image.

        Returns:
            Dict with keys:
                category    – Predicted expense category.
                amount      – Best extracted bill total (float).
                all_amounts – All detected monetary values (list[float], desc).
                raw_text    – Raw OCR output.
                cleaned_text– Text after noise removal, used for classification.
                ocr_backend – Name of the OCR backend used.

        Raises:
            FileNotFoundError: Image file does not exist.
            RuntimeError:      No usable model is available.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Prefer end-to-end model when available
        if self.receipt_model is not None:
            result = self._predict_with_receipt_model(image_path)
            if result is not None:
                self.loaded_backend = result["ocr_backend"]
                return result

        # Legacy pipeline
        if not all([self.model, self.vectorizer, self.encoder]):
            raise RuntimeError(
                "No receipt model is configured. Set RECEIPT_MODEL_MODULE to your "
                "model adapter, or enable ALLOW_LEGACY_FALLBACK to use the legacy pipeline."
            )

        raw_text = self.extract_text(image_path)
        cleaned_text = self.clean_text(raw_text)
        category = self.predict_category(cleaned_text)
        category = self.refine_category(raw_text, category)
        all_amounts, bill_amount = self.extract_bill_amount(raw_text)

        return {
            "category": category,
            "amount": bill_amount,
            "all_amounts": all_amounts,
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "ocr_backend": self.loaded_backend,
        }


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        service = OCRService()
        logger.info("OCR Service loaded successfully (backend=%s)", service.ocr_backend)
        if service.encoder:
            logger.info("Categories: %s", list(service.encoder.classes_))
    except Exception as exc:
        logger.error("Error loading OCR Service: %s", exc)
