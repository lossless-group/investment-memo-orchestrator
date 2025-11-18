"""
Brand configuration system for customizable memo exports.

Supports multiple brand configurations in the same project:
- brand-config.yaml (default)
- brand-<name>-config.yaml (specific brands)

Usage:
    # Load default config
    brand = BrandConfig.load()

    # Load specific brand
    brand = BrandConfig.load(brand_name="accel")

    # Load from custom path
    brand = BrandConfig.load(config_path=Path("custom.yaml"))
"""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import yaml


@dataclass
class BrandColors:
    """Brand color palette (hex codes)."""
    primary: str
    secondary: str
    text_dark: str
    text_light: str
    background: str
    background_alt: str


@dataclass
class BrandFonts:
    """Font configuration.

    Supports separate fonts for headers and body text.
    Paths are relative to project root.
    """
    # Body text font (paragraphs, lists, etc.)
    family: str
    fallback: str
    custom_fonts_dir: Optional[str] = None

    # Optional: separate font for headers
    header_family: Optional[str] = None
    header_fallback: Optional[str] = None
    header_fonts_dir: Optional[str] = None


@dataclass
class BrandCompany:
    """Company information."""
    name: str
    tagline: str
    confidential_footer: str


@dataclass
class BrandConfig:
    """Complete brand configuration."""
    company: BrandCompany
    colors: BrandColors
    fonts: BrandFonts

    @classmethod
    def load(
        cls,
        brand_name: Optional[str] = None,
        config_path: Optional[Path] = None
    ) -> 'BrandConfig':
        """Load brand configuration from YAML file.

        Args:
            brand_name: Name of brand (loads brand-{name}-config.yaml)
            config_path: Direct path to config file (overrides brand_name)

        Returns:
            BrandConfig instance

        Priority:
            1. config_path if provided
            2. brand-{brand_name}-config.yaml if brand_name provided
            3. brand-config.yaml (default)
            4. Hypernova defaults (if no config found)

        Examples:
            >>> BrandConfig.load()  # Uses brand-config.yaml or defaults
            >>> BrandConfig.load(brand_name="accel")  # Uses brand-accel-config.yaml
            >>> BrandConfig.load(config_path=Path("custom.yaml"))
        """
        if config_path is None:
            if brand_name:
                # Look in templates/brand-configs/ first, then root directory
                config_path = Path(f"templates/brand-configs/brand-{brand_name}-config.yaml")
                if not config_path.exists():
                    config_path = Path(f"brand-{brand_name}-config.yaml")
            else:
                # Look for default config in templates/brand-configs/ first
                config_path = Path("templates/brand-configs/brand-config.yaml")
                if not config_path.exists():
                    config_path = Path("brand-config.yaml")

        if not config_path.exists():
            if brand_name or (config_path != Path("brand-config.yaml")):
                # User specified a brand but file doesn't exist
                raise FileNotFoundError(
                    f"Brand config not found: {config_path}\n"
                    f"Create the file or use --brand flag with an existing brand."
                )
            # No config specified, use defaults
            print(f"⚠️  Brand config not found: {config_path}")
            print("   Using default Hypernova branding.")
            print("   Create brand-config.yaml to customize.")
            return cls.get_default_config()

        print(f"✓ Loading brand config: {config_path}")

        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {config_path}: {e}")

        # Validate required sections
        required = ['company', 'colors', 'fonts']
        missing = [section for section in required if section not in data]
        if missing:
            raise ValueError(
                f"Missing required sections in {config_path}: {', '.join(missing)}"
            )

        try:
            return cls(
                company=BrandCompany(**data['company']),
                colors=BrandColors(**data['colors']),
                fonts=BrandFonts(**data['fonts'])
            )
        except TypeError as e:
            raise ValueError(
                f"Invalid brand config structure in {config_path}: {e}\n"
                f"See brand-config.example.yaml for correct format."
            )

    @classmethod
    def get_default_config(cls) -> 'BrandConfig':
        """Return Hypernova Capital default branding."""
        return cls(
            company=BrandCompany(
                name="Hypernova Capital",
                tagline="Network-Driven | High-impact | Transformative venture fund",
                confidential_footer="This document is confidential and proprietary to {company_name}."
            ),
            colors=BrandColors(
                primary="#1a3a52",      # Navy
                secondary="#1dd3d3",    # Cyan
                text_dark="#1a2332",    # Almost black
                text_light="#6b7280",   # Gray
                background="#ffffff",   # White
                background_alt="#f0f0eb"  # Cream
            ),
            fonts=BrandFonts(
                family="Arboria",
                fallback="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                custom_fonts_dir="templates/fonts/Arboria"
            )
        )

    def list_available_brands(self) -> list[str]:
        """List all available brand configurations.

        Looks in templates/brand-configs/ directory first, then root directory.

        Returns:
            List of brand names (without 'brand-' prefix and '-config.yaml' suffix)
        """
        brands = []

        # Check templates/brand-configs/ directory
        brand_configs_dir = Path("templates/brand-configs")
        if brand_configs_dir.exists():
            for config in brand_configs_dir.glob("brand-*-config.yaml"):
                name = config.name.replace("brand-", "").replace("-config.yaml", "")
                brands.append(name)

        # Check root directory (for backward compatibility)
        for config in Path(".").glob("brand-*-config.yaml"):
            name = config.name.replace("brand-", "").replace("-config.yaml", "")
            if name not in brands:  # Avoid duplicates
                brands.append(name)

        return sorted(brands)


def validate_color(color: str) -> bool:
    """Validate hex color format."""
    if not color.startswith("#"):
        return False
    if len(color) not in [4, 7]:  # #RGB or #RRGGBB
        return False
    try:
        int(color[1:], 16)
        return True
    except ValueError:
        return False


def validate_brand_config(config: BrandConfig) -> list[str]:
    """Validate brand configuration and return list of warnings.

    Returns:
        List of warning messages (empty if all valid)
    """
    warnings = []

    # Validate colors
    color_fields = [
        ('primary', config.colors.primary),
        ('secondary', config.colors.secondary),
        ('text_dark', config.colors.text_dark),
        ('text_light', config.colors.text_light),
        ('background', config.colors.background),
        ('background_alt', config.colors.background_alt),
    ]

    for field_name, color_value in color_fields:
        if not validate_color(color_value):
            warnings.append(
                f"Invalid color '{field_name}': {color_value} "
                f"(should be hex format like #1a3a52)"
            )

    # Validate body text custom fonts directory if specified
    if config.fonts.custom_fonts_dir:
        fonts_dir = Path(config.fonts.custom_fonts_dir)
        if not fonts_dir.exists():
            warnings.append(
                f"Body font directory not found: {fonts_dir}\n"
                f"  Will fall back to system fonts."
            )
        else:
            # Check for at least one font file
            font_files = list(fonts_dir.glob("*.woff2"))
            if not font_files:
                warnings.append(
                    f"No .woff2 font files found in: {fonts_dir}\n"
                    f"  Will fall back to system fonts."
                )

    # Validate header fonts directory if specified
    if config.fonts.header_fonts_dir:
        header_fonts_dir = Path(config.fonts.header_fonts_dir)
        if not header_fonts_dir.exists():
            warnings.append(
                f"Header font directory not found: {header_fonts_dir}\n"
                f"  Will fall back to body font or system fonts."
            )
        else:
            # Check for at least one font file
            header_font_files = list(header_fonts_dir.glob("*.woff2"))
            if not header_font_files:
                warnings.append(
                    f"No .woff2 font files found in: {header_fonts_dir}\n"
                    f"  Will fall back to body font or system fonts."
                )

    # Validate company name not empty
    if not config.company.name.strip():
        warnings.append("Company name is empty")

    return warnings
