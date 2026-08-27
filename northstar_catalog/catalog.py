"""Catalog validation shared by NorthStar Prime and SpaceCash daemon."""

import json
import os
import sqlite3
import hashlib
from pathlib import Path


class ProductNotFound(ValueError):
    pass


class ProductNotEligible(ValueError):
    pass


def is_restricted_product(name="", description="", category="", brand_slug=""):
    blob = f"{name} {description} {category} {brand_slug}".lower()
    return any(x in blob for x in ("thc", "cannabis", "delta-8", "delta8", "delta-9", "delta9", "rso-infused", "adult-use"))


def is_meditation_content(name="", description="", brand_slug=""):
    blob = f"{name} {description} {brand_slug}".lower()
    return any(x in blob for x in (
        "meditation", "binaural", "isochronic", "theta", "alpha", "delta waves",
        "guided", "stress release", "focus flow", "body scan", "ocean of consciousness",
    ))


def is_novella_content(name="", description="", brand_slug=""):
    blob = f"{name} {description} {brand_slug}".lower()
    return any(x in blob for x in ("novella", "emoji soup", "hitchhiker", "cookbook for hitchhikers"))


CHECKOUT_HOLD_SLUGS = {
    "color-outside-mind-horror": "This edition is still marked coming soon.",
    "color-outside-mind-sacred": "This edition is still marked coming soon.",
    "color-outside-mind-trilogy": "This bundle includes editions that are not yet public-sale ready.",
    "renaltrack-lab-tracker": "This app concept is being merged into RenalShield.",
    "dialysispal-companion-app": "This app concept is being merged into RenalShield.",
    "esrd-survival-kit": "Synchronize RenalShield branding with the external Gumroad listing.",
    "dialysis-partners-guide": "Synchronize RenalShield branding with the external Gumroad listing.",
    "newly-diagnosed-ckd-guide": "Synchronize RenalShield branding with the external Gumroad listing.",
    "ckd-kitchen-cookbook": "Synchronize RenalShield branding with the external Gumroad listing.",
    "renalwise-complete-kidney-health-bundle": "Synchronize RenalShield branding with the external Gumroad listing.",
    "renalwise-printable-bundle": "Synchronize RenalShield branding with the external Gumroad listing.",
    "color-outside-mind-psychedelic": "The Amazon listing requires manual availability verification.",
    "brick-moc-third-eye": "Reverify the eBay listing price and inventory before storefront release.",
    "brick-moc-samhain": "Reverify the eBay listing price and inventory before storefront release.",
    "brick-moc-graveyard": "The eBay price no longer matches the storefront seed.",
    "brick-moc-christmas-tree": "Reverify the eBay listing price and inventory before storefront release.",
    "brick-moc-good-fortune": "Reverify the eBay listing price and inventory before storefront release.",
    "brick-moc-oregon-ducks": "The eBay price no longer matches the storefront seed.",
}


PUBLIC_SALE_READY_STATES = frozenset({
    "public_ready",
    "ready_for_public_sale",
    "retail_ready",
})
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_REGISTRY = REPO_ROOT / "data" / "nsp_product_release_registry.json"
_RELEASE_REGISTRY_CACHE = {"key": None, "products": {}}


def load_product_release_registry(path=None):
    """Load the explicit paid-release registry, cached by path and file stamp."""
    registry_path = Path(
        path
        or os.environ.get("NSP_PRODUCT_RELEASE_REGISTRY", "")
        or DEFAULT_RELEASE_REGISTRY
    )
    try:
        stat = registry_path.stat()
        key = (str(registry_path.resolve()), stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (str(registry_path.resolve()), None, None)
    if _RELEASE_REGISTRY_CACHE.get("key") == key:
        return dict(_RELEASE_REGISTRY_CACHE.get("products") or {})
    products = {}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        raw_products = payload.get("products", payload) if isinstance(payload, dict) else {}
        if isinstance(raw_products, dict):
            products = {
                str(slug).strip().lower(): entry
                for slug, entry in raw_products.items()
                if isinstance(entry, dict)
            }
    except (OSError, UnicodeError, json.JSONDecodeError):
        products = {}
    _RELEASE_REGISTRY_CACHE.update({"key": key, "products": dict(products)})
    return products


def release_registry_evidence_reasons(
    slug="",
    source="",
    *,
    release_registry_path=None,
    require_card_art=True,
):
    """Return reasons an explicit paid-release registry entry is incomplete."""
    normalized_slug = str(slug or "").strip().lower()
    entry = load_product_release_registry(release_registry_path).get(normalized_slug)
    if not entry:
        return ["missing explicit release-registry entry"]
    reasons = []
    if str(entry.get("status") or "").strip().lower() not in PUBLIC_SALE_READY_STATES:
        reasons.append("registry status is not public-sale ready")
    entry_source = str(entry.get("source") or "").strip().lower()
    normalized_source = str(source or "").strip().lower()
    if entry_source and normalized_source and entry_source != normalized_source:
        reasons.append("registry source does not match catalog source")
    if entry.get("artifact_verified") is not True:
        reasons.append("artifact_verified is not true")
    if entry.get("manifest_verified") is not True:
        reasons.append("manifest_verified is not true")
    if require_card_art and entry.get("card_art_verified") is not True:
        reasons.append("card_art_verified is not true")
    for key in ("artifact", "manifest", "card_art"):
        if key == "card_art" and not require_card_art:
            continue
        raw_path = entry.get(key)
        if not raw_path:
            reasons.append(f"{key} path is missing")
            continue
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        if not candidate.is_file():
            reasons.append(f"{key} path does not exist")
            continue
        declared_hash = str(entry.get(f"{key}_sha256") or "").strip().upper()
        if declared_hash:
            digest = hashlib.sha256()
            try:
                with candidate.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
            except OSError:
                reasons.append(f"{key} path cannot be hashed")
                continue
            if digest.hexdigest().upper() != declared_hash:
                reasons.append(f"{key} SHA-256 does not match registry")
    return reasons


def checkout_hold_reason(
    name="",
    description="",
    slug="",
    readiness="",
    missing_before_public="",
    source="",
    release_registry_path=None,
    legacy_schema=False,
):
    """Return a public-sale hold reason, or None when checkout is eligible.

    legacy_schema: the source DB predates the readiness/evidence columns, so the
    explicit-evidence requirements cannot apply; only content/slug holds do.
    """
    normalized_slug = str(slug or "").strip().lower()
    if normalized_slug in CHECKOUT_HOLD_SLUGS:
        return CHECKOUT_HOLD_SLUGS[normalized_slug]

    blob = f"{name} {description}".lower()
    if "coming soon" in blob or "pre-ready" in blob:
        return "This product is still marked as pending release."

    public_gates = str(missing_before_public or "").strip()
    normalized_readiness = str(readiness or "").strip().lower()
    if public_gates:
        return f"Public-release gates remain: {public_gates}"
    if normalized_readiness and normalized_readiness not in PUBLIC_SALE_READY_STATES:
        return f"Catalog readiness is {normalized_readiness}; public-sale approval is required."
    normalized_source = str(source or "").strip().lower()
    if legacy_schema:
        return None
    if normalized_source == "chromatic" and normalized_readiness not in PUBLIC_SALE_READY_STATES:
        return (
            "Explicit public-sale readiness and fulfillment evidence are not "
            "recorded for this product."
        )
    if normalized_source in {"prime", "chromatic"} and release_registry_evidence_reasons(
        normalized_slug,
        normalized_source,
        release_registry_path=release_registry_path,
    ):
        return (
            "Explicit public-sale approval and verified fulfillment evidence "
            "are not recorded "
            "for this product."
        )
    return None


def prime_shop_category(row):
    blob = f"{row.get('brand_slug', '')} {row.get('name', '')} {row.get('description') or ''}".lower()
    if row.get("brand_slug") == "brick-moc" or any(x in blob for x in ("lego", "moc", "brick mosaic", "brick-mosaic")):
        return "brick_moc"
    if "coloring" in blob:
        return "coloring"
    if any(x in blob for x in ("tcg", "card deck", "oracle deck")):
        return "tcg"
    if any(x in blob for x in ("print", "mosaic", "art")):
        return "print"
    if any(x in blob for x in ("commission", "custom")):
        return "commission"
    if row.get("brand_slug") == "biolume":
        return "biolume_art"
    if row.get("brand_slug") == "idc-studios":
        return "idc_media"
    if row.get("brand_slug") == "pneumalumana":
        return "pneumalumana"
    if row.get("brand_slug") == "9i-productions":
        return "audio"
    if any(x in blob for x in ("generator", "kit", "blueprint")):
        return "tools_kits"
    return "northstar"


class NorthStarCatalog:
    def __init__(self, prime_db_path, chromatic_db_path=None):
        self.prime_db_path = Path(prime_db_path)
        self.chromatic_db_path = Path(chromatic_db_path) if chromatic_db_path else None

    def _connect(self, path):
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn

    def lookup_checkout_product(self, source, product_id):
        source = (source or "").strip().lower()
        product_id = int(product_id)
        if source == "prime":
            return self._lookup_prime(product_id)
        if source == "chromatic":
            return self._lookup_chromatic(product_id)
        return None

    def require_spacecash_product(self, source, product_id):
        product = self.lookup_checkout_product(source, product_id)
        if not product:
            raise ProductNotFound("SpaceCash product not found.")
        if product.get("restricted"):
            raise ProductNotEligible("This product requires compliance review before checkout.")
        if product.get("checkout_hold_reason"):
            raise ProductNotEligible(product["checkout_hold_reason"])
        price = float(product.get("price") or 0)
        if price <= 0:
            raise ProductNotEligible("This product does not require SpaceCash payment.")
        return product

    def _lookup_prime(self, product_id):
        if not self.prime_db_path.exists():
            return None
        conn = self._connect(self.prime_db_path)
        try:
            row = conn.execute(
                """
                SELECT p.id, p.slug, p.name, p.description, p.price, p.external_url,
                       b.slug AS brand_slug
                FROM products p
                JOIN brands b ON p.brand_id = b.id
                WHERE p.id = ? AND p.is_active = 1
                """,
                (product_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["source"] = "prime"
            data["category"] = prime_shop_category(data)
            data["restricted"] = is_restricted_product(
                data.get("name", ""),
                data.get("description", ""),
                data.get("category", ""),
                data.get("brand_slug", ""),
            )
            data["meditation"] = is_meditation_content(data.get("name", ""), data.get("description", ""), data.get("brand_slug", ""))
            data["novella"] = is_novella_content(data.get("name", ""), data.get("description", ""), data.get("brand_slug", ""))
            data["checkout_hold_reason"] = (
                checkout_hold_reason(
                    data.get("name", ""),
                    data.get("description", ""),
                    data.get("slug", ""),
                    source="prime",
                )
                if float(data.get("price") or 0) > 0
                else None
            )
            return data
        finally:
            conn.close()

    def _lookup_chromatic(self, product_id):
        if not self.chromatic_db_path or not self.chromatic_db_path.exists():
            return None
        conn = self._connect(self.chromatic_db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
            readiness_sql = "readiness" if "readiness" in columns else "NULL AS readiness"
            gates_sql = (
                "missing_before_public"
                if "missing_before_public" in columns
                else "NULL AS missing_before_public"
            )
            row = conn.execute(
                f"""
                SELECT id, slug, name, description, price, buy_link AS external_url,
                       category, brand, {readiness_sql}, {gates_sql}
                FROM products
                WHERE id = ?
                """,
                (product_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["source"] = "chromatic"
            data["brand_slug"] = data.get("brand") or "chromatic"
            data["restricted"] = is_restricted_product(
                data.get("name", ""),
                data.get("description", ""),
                data.get("category", ""),
                data.get("brand", ""),
            )
            data["meditation"] = is_meditation_content(data.get("name", ""), data.get("description", ""), data.get("brand_slug", ""))
            data["novella"] = is_novella_content(data.get("name", ""), data.get("description", ""), data.get("brand_slug", ""))
            data["checkout_hold_reason"] = (
                checkout_hold_reason(
                    data.get("name", ""),
                    data.get("description", ""),
                    data.get("slug", ""),
                    data.get("readiness", ""),
                    data.get("missing_before_public", ""),
                    source="chromatic",
                    legacy_schema="readiness" not in columns,
                )
                if float(data.get("price") or 0) > 0
                else None
            )
            return data
        except sqlite3.Error:
            return None
        finally:
            conn.close()
