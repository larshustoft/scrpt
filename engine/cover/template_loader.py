"""
Cover Template Loader
======================
Loads niche-specific cover templates from the filesystem.
Falls back to inline NICHE_TEMPLATES dict for niches that
have not yet been migrated to file-based templates.

Directory structure per niche:
    templates/{niche}/
        style.css       - CSS for this niche (root-level fallback)
        front.html      - Front cover HTML
        back.html       - Back cover HTML
        spine.html      - Spine HTML
        spec.json       - Design specification
        references/     - Benchmark images from Amazon bestsellers
        variants/       - Multiple design variants
            v1/
                variant.json  - Variant metadata (name, reference, description)
                style.css     - Variant-specific CSS
                front.html    - Variant-specific front cover
                back.html     - Variant-specific back cover
                spine.html    - Variant-specific spine
            v2/ ...
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from ..config import TEMPLATES_DIR


@dataclass
class CoverTemplate:
    """A loaded cover template ready for rendering."""
    niche: str
    template_css: str
    front_cover_html: str
    back_cover_html: str
    spine_html: str
    spec: dict = field(default_factory=dict)
    source: str = "file"  # "file" or "inline"


@dataclass
class VariantInfo:
    """Metadata for a single design variant within a niche."""
    variant_id: str          # "v1", "v2", etc.
    name: str                # "Dark Navy & Gold"
    reference_filename: str  # "ref_01.jpg" — links to niche's references/ dir
    description: str
    inspired_by: str


@dataclass
class DesignSpec:
    """Parsed design specification for a niche."""
    niche: str
    data: dict
    reference_images: list  # list of Path objects

    @property
    def display_name(self) -> str:
        return self.data.get("display_name", self.niche)

    @property
    def references_dir(self) -> Path:
        return TEMPLATES_DIR / self.niche / "references"


class TemplateLoader:
    """
    Loads cover templates from the filesystem template directory.

    Fallback chain:
        1. File-based template for the requested niche
        2. File-based "default" template
        3. Inline NICHE_TEMPLATES dict (from renderer.py)
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self._cache: dict[tuple[str, Optional[str]], CoverTemplate] = {}
        self._spec_cache: dict[str, DesignSpec] = {}
        self._base_html: Optional[str] = None
        self._base_css: Optional[str] = None

    def _niche_dir(self, niche: str) -> Path:
        return self.templates_dir / niche

    def _has_file_template(self, niche: str) -> bool:
        """Check if a niche has been migrated to file-based templates."""
        d = self._niche_dir(niche)
        return (
            (d / "style.css").exists()
            and (d / "front.html").exists()
            and (d / "back.html").exists()
            and (d / "spine.html").exists()
        )

    def load_base_html(self) -> str:
        """Load the base HTML skeleton from _base/base.html."""
        if self._base_html is None:
            base_path = self.templates_dir / "_base" / "base.html"
            if base_path.exists():
                self._base_html = base_path.read_text(encoding="utf-8")
            else:
                # Fallback: use the inline COVER_TEMPLATE_HTML
                from .renderer import COVER_TEMPLATE_HTML
                self._base_html = COVER_TEMPLATE_HTML.template
        return self._base_html

    def load_base_css(self) -> str:
        """Load shared base CSS from _base/base.css."""
        if self._base_css is None:
            base_path = self.templates_dir / "_base" / "base.css"
            if base_path.exists():
                self._base_css = base_path.read_text(encoding="utf-8")
            else:
                self._base_css = ""
        return self._base_css

    def load_template(self, niche: str, variant_id: Optional[str] = None) -> CoverTemplate:
        """
        Load a niche template. Tries file-based first, falls back to inline.

        Args:
            niche: Book type key (e.g., "word_search", "sudoku")
            variant_id: Optional variant ID (e.g., "v1", "v2"). If provided,
                loads from templates/{niche}/variants/{variant_id}/.

        Returns:
            CoverTemplate with all HTML/CSS loaded
        """
        cache_key = (niche, variant_id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # If variant_id is an archetype reference, delegate to load_archetype
        if variant_id and variant_id.startswith("arch_"):
            # Format: "arch_{archetype_id}_{theme}" e.g. "arch_bold-stack_dark"
            parts = variant_id.split("_", 2)  # ["arch", "archetype-id", "theme"]
            if len(parts) >= 3:
                archetype_id = parts[1]
                theme = parts[2]
            else:
                archetype_id = parts[1] if len(parts) > 1 else "bold-stack"
                theme = "dark"
            try:
                template = self.load_archetype(niche, archetype_id, theme)
                self._cache[cache_key] = template
                return template
            except FileNotFoundError:
                pass  # Fall through to normal variant loading

        # If a variant_id is specified, try loading from variants/ subdir
        if variant_id:
            variant_dir = self._niche_dir(niche) / "variants" / variant_id
            if self._has_file_template_in_dir(variant_dir):
                template = self._load_from_dir(variant_dir, niche)
                self._cache[cache_key] = template
                return template
            # Variant not found — fall through to root-level niche template

        if self._has_file_template(niche):
            template = self._load_from_files(niche)
        elif self._has_file_template("default"):
            # Niche not found in files, try default file template
            template = self._load_from_files("default")
            template.niche = niche
        else:
            # Fall back to inline NICHE_TEMPLATES
            template = self._load_from_inline(niche)

        self._cache[cache_key] = template
        return template

    def _has_file_template_in_dir(self, d: Path) -> bool:
        """Check if a directory contains a complete template (style.css + HTML files)."""
        return (
            d.is_dir()
            and (d / "style.css").exists()
            and (d / "front.html").exists()
            and (d / "back.html").exists()
            and (d / "spine.html").exists()
        )

    def _load_from_dir(self, d: Path, niche: str) -> CoverTemplate:
        """Load template from an arbitrary directory (used for variants)."""
        style_css = (d / "style.css").read_text(encoding="utf-8")
        front_html = (d / "front.html").read_text(encoding="utf-8")
        back_html = (d / "back.html").read_text(encoding="utf-8")
        spine_html = (d / "spine.html").read_text(encoding="utf-8")

        # Prepend base CSS if it exists
        base_css = self.load_base_css()
        if base_css:
            style_css = base_css + "\n" + style_css

        # Resolve artwork.png to absolute file:// URL for Playwright rendering
        artwork_path = d / "artwork.png"
        if artwork_path.exists():
            abs_url = artwork_path.resolve().as_uri()
            style_css = style_css.replace("url('artwork.png')", f"url('{abs_url}')")
            style_css = style_css.replace('url("artwork.png")', f'url("{abs_url}")')

        spec = {}
        spec_path = d / "variant.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text(encoding="utf-8"))

        return CoverTemplate(
            niche=niche,
            template_css=style_css,
            front_cover_html=front_html,
            back_cover_html=back_html,
            spine_html=spine_html,
            spec=spec,
            source="file",
        )

    def _load_from_files(self, niche: str) -> CoverTemplate:
        """Load template from filesystem."""
        d = self._niche_dir(niche)

        style_css = (d / "style.css").read_text(encoding="utf-8")
        front_html = (d / "front.html").read_text(encoding="utf-8")
        back_html = (d / "back.html").read_text(encoding="utf-8")
        spine_html = (d / "spine.html").read_text(encoding="utf-8")

        # Prepend base CSS if it exists
        base_css = self.load_base_css()
        if base_css:
            style_css = base_css + "\n" + style_css

        spec = {}
        spec_path = d / "spec.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text(encoding="utf-8"))

        return CoverTemplate(
            niche=niche,
            template_css=style_css,
            front_cover_html=front_html,
            back_cover_html=back_html,
            spine_html=spine_html,
            spec=spec,
            source="file",
        )

    def _load_from_inline(self, niche: str) -> CoverTemplate:
        """Fall back to inline NICHE_TEMPLATES dict."""
        from .renderer import NICHE_TEMPLATES

        data = NICHE_TEMPLATES.get(niche, NICHE_TEMPLATES["default"])
        return CoverTemplate(
            niche=niche,
            template_css=data["template_css"],
            front_cover_html=data["front_cover_html"],
            back_cover_html=data["back_cover_html"],
            spine_html=data["spine_html"],
            source="inline",
        )

    def load_spec(self, niche: str) -> Optional[DesignSpec]:
        """Load the design specification for a niche."""
        if niche in self._spec_cache:
            return self._spec_cache[niche]

        spec_path = self._niche_dir(niche) / "spec.json"
        if not spec_path.exists():
            return None

        data = json.loads(spec_path.read_text(encoding="utf-8"))
        ref_dir = self._niche_dir(niche) / "references"
        if ref_dir.exists():
            ref_images = sorted(
                p for p in ref_dir.iterdir()
                if p.name.startswith("ref_") and p.suffix.lower() in (".png", ".jpg", ".jpeg")
            )
        else:
            ref_images = []

        spec = DesignSpec(niche=niche, data=data, reference_images=ref_images)
        self._spec_cache[niche] = spec
        return spec

    def list_variants(self, niche: str) -> list[VariantInfo]:
        """
        List all available design variants for a niche.

        Scans templates/{niche}/variants/ for subdirs containing variant.json.
        Returns list sorted by variant_id. Empty list if no variants exist.
        """
        variants_dir = self._niche_dir(niche) / "variants"
        if not variants_dir.exists() or not variants_dir.is_dir():
            return []

        result = []
        for d in sorted(variants_dir.iterdir()):
            if not d.is_dir():
                continue
            variant_json = d / "variant.json"
            if not variant_json.exists():
                continue
            try:
                data = json.loads(variant_json.read_text(encoding="utf-8"))
                result.append(VariantInfo(
                    variant_id=d.name,
                    name=data.get("name", d.name),
                    reference_filename=data.get("reference", ""),
                    description=data.get("description", ""),
                    inspired_by=data.get("inspired_by", ""),
                ))
            except (json.JSONDecodeError, KeyError):
                continue

        return result

    # ── Archetype support ───────────────────────────────────────

    def load_archetype(self, niche: str, archetype_id: str, theme: str = "dark") -> CoverTemplate:
        """
        Load an archetype template with theme color variables injected.

        Archetypes live in templates/{niche}/archetypes/{archetype_id}/.
        Theme colors are defined in archetype.json and injected as CSS custom properties.
        """
        cache_key = (niche, f"arch_{archetype_id}_{theme}")
        if cache_key in self._cache:
            return self._cache[cache_key]

        arch_dir = self.templates_dir / niche / "archetypes" / archetype_id
        archetype_json_path = arch_dir / "archetype.json"
        if not archetype_json_path.exists():
            raise FileNotFoundError(f"Archetype not found: {niche}/{archetype_id}")

        meta = json.loads(archetype_json_path.read_text(encoding="utf-8"))
        themes = meta.get("themes", {})
        theme_vars = themes.get(theme, themes.get("dark", {}))

        # Build CSS: theme variables + base CSS + archetype CSS
        theme_css = ":root {\n" + "\n".join(f"  {k}: {v};" for k, v in theme_vars.items()) + "\n}\n"
        base_css = self.load_base_css()
        arch_css = (arch_dir / "style.css").read_text(encoding="utf-8")
        full_css = theme_css + "\n" + base_css + "\n" + arch_css

        front = (arch_dir / "front.html").read_text(encoding="utf-8")
        back = (arch_dir / "back.html").read_text(encoding="utf-8")
        spine = (arch_dir / "spine.html").read_text(encoding="utf-8")

        template = CoverTemplate(
            niche=niche,
            template_css=full_css,
            front_cover_html=front,
            back_cover_html=back,
            spine_html=spine,
            spec=meta,
            source="archetype",
        )
        self._cache[cache_key] = template
        return template

    def list_archetypes(self, niche: str) -> list[dict]:
        """List available archetypes for a book type with their theme data."""
        arch_dir = self.templates_dir / niche / "archetypes"
        if not arch_dir.exists():
            return []
        result = []
        for d in sorted(arch_dir.iterdir()):
            if not d.is_dir():
                continue
            json_path = d / "archetype.json"
            if not json_path.exists():
                continue
            try:
                meta = json.loads(json_path.read_text(encoding="utf-8"))
                result.append({"archetype_id": d.name, **meta})
            except (json.JSONDecodeError, KeyError):
                continue
        return result

    def list_niches(self) -> list[dict]:
        """List all available niche templates with their status."""
        from .renderer import NICHE_TEMPLATES

        # Collect all known niches from both sources
        all_niches = set(NICHE_TEMPLATES.keys())
        if self.templates_dir.exists():
            for d in self.templates_dir.iterdir():
                if d.is_dir() and not d.name.startswith("_"):
                    all_niches.add(d.name)

        result = []
        for niche in sorted(all_niches):
            has_files = self._has_file_template(niche)
            has_inline = niche in NICHE_TEMPLATES
            spec = self.load_spec(niche)
            ref_count = len(spec.reference_images) if spec else 0

            variants = self.list_variants(niche)
            result.append({
                "niche": niche,
                "source": "file" if has_files else "inline",
                "has_spec": spec is not None,
                "reference_count": ref_count,
                "variant_count": len(variants),
                "has_inline_fallback": has_inline,
            })
        return result

    def invalidate_cache(self, niche: Optional[str] = None):
        """Clear cache for a niche (or all) to pick up file changes."""
        if niche:
            # Remove all cache entries for this niche (any variant)
            keys_to_remove = [k for k in self._cache if k[0] == niche]
            for k in keys_to_remove:
                del self._cache[k]
            self._spec_cache.pop(niche, None)
        else:
            self._cache.clear()
            self._spec_cache.clear()
            self._base_html = None
            self._base_css = None


# Module-level singleton
_loader: Optional[TemplateLoader] = None


def get_template_loader() -> TemplateLoader:
    """Get the singleton TemplateLoader instance."""
    global _loader
    if _loader is None:
        _loader = TemplateLoader()
    return _loader
