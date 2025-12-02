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
    google_fonts_url: Optional[str] = None  # Google Fonts link for body font
    weight: int = 400  # Default font weight for body text (400=normal, 500=medium, 700=bold)

    # Optional: separate font for headers
    header_family: Optional[str] = None
    header_fallback: Optional[str] = None
    header_fonts_dir: Optional[str] = None
    header_google_fonts_url: Optional[str] = None  # Google Fonts link for header font
    header_weight: int = 700  # Default font weight for headers


@dataclass
class BrandCompany:
    """Company information."""
    name: str
    tagline: str
    confidential_footer: str


@dataclass
class BrandLogo:
    """Logo configuration with theme support."""
    light_mode: Optional[str] = None
    dark_mode: Optional[str] = None
    width: str = "180px"
    height: str = "60px"
    alt: str = ""


@dataclass
class BrandConfig:
    """Complete brand configuration."""
    company: BrandCompany
    colors: BrandColors
    fonts: BrandFonts
    logo: Optional[BrandLogo] = None

    @classmethod
    def load(
        cls,
        brand_name: Optional[str] = None,
        config_path: Optional[Path] = None,
        firm: Optional[str] = None
    ) -> 'BrandConfig':
        """Load brand configuration from YAML file.

        Args:
            brand_name: Name of brand (loads brand-{name}-config.yaml)
            config_path: Direct path to config file (overrides brand_name)
            firm: Firm name to check io/{firm}/configs/ for brand configs

        Returns:
            BrandConfig instance

        Priority:
            1. config_path if provided
            2. io/{firm}/configs/brand-{brand_name}-config.yaml (if firm provided)
            3. templates/brand-configs/brand-{brand_name}-config.yaml
            4. brand-{brand_name}-config.yaml (root directory)
            5. brand-config.yaml (default)
            6. Hypernova defaults (if no config found)

        Examples:
            >>> BrandConfig.load()  # Uses brand-config.yaml or defaults
            >>> BrandConfig.load(brand_name="accel")  # Uses brand-accel-config.yaml
            >>> BrandConfig.load(brand_name="hypernova", firm="hypernova")  # Checks io/hypernova/configs/ first
            >>> BrandConfig.load(config_path=Path("custom.yaml"))
        """
        if config_path is None:
            if brand_name:
                # Priority order for brand-specific configs:
                # 1. Firm-scoped: io/{firm}/configs/brand-{name}-config.yaml
                # 2. Templates: templates/brand-configs/brand-{name}-config.yaml
                # 3. Root: brand-{name}-config.yaml
                search_paths = []

                if firm:
                    firm_config = Path(f"io/{firm}/configs/brand-{brand_name}-config.yaml")
                    search_paths.append(firm_config)

                search_paths.append(Path(f"templates/brand-configs/brand-{brand_name}-config.yaml"))
                search_paths.append(Path(f"brand-{brand_name}-config.yaml"))

                # Find first existing config
                config_path = None
                for path in search_paths:
                    if path.exists():
                        config_path = path
                        break

                # If none found, use last path for error message
                if config_path is None:
                    config_path = search_paths[-1]
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
            # Parse logo configuration if present
            logo = None
            if 'logo' in data:
                logo = BrandLogo(**data['logo'])

            return cls(
                company=BrandCompany(**data['company']),
                colors=BrandColors(**data['colors']),
                fonts=BrandFonts(**data['fonts']),
                logo=logo
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

    def list_available_brands(self, firm: Optional[str] = None) -> list[str]:
        """List all available brand configurations.

        Looks in firm-scoped configs, templates/brand-configs/, then root directory.

        Args:
            firm: Optional firm name to check io/{firm}/configs/ for brand configs

        Returns:
            List of brand names (without 'brand-' prefix and '-config.yaml' suffix)
        """
        brands = []

        # Check firm-scoped configs first (highest priority)
        if firm:
            firm_configs_dir = Path(f"io/{firm}/configs")
            if firm_configs_dir.exists():
                for config in firm_configs_dir.glob("brand-*-config.yaml"):
                    name = config.name.replace("brand-", "").replace("-config.yaml", "")
                    brands.append(name)

        # Check templates/brand-configs/ directory
        brand_configs_dir = Path("templates/brand-configs")
        if brand_configs_dir.exists():
            for config in brand_configs_dir.glob("brand-*-config.yaml"):
                name = config.name.replace("brand-", "").replace("-config.yaml", "")
                if name not in brands:  # Avoid duplicates
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

    # Validate logo paths if specified
    if config.logo:
        if config.logo.light_mode:
            # Only validate local paths, not URLs
            if not config.logo.light_mode.startswith(('http://', 'https://')):
                light_logo_path = Path(config.logo.light_mode)
                if not light_logo_path.exists():
                    warnings.append(
                        f"Light mode logo not found: {light_logo_path}\n"
                        f"  Will use text-based logo instead."
                    )
        if config.logo.dark_mode:
            # Only validate local paths, not URLs
            if not config.logo.dark_mode.startswith(('http://', 'https://')):
                dark_logo_path = Path(config.logo.dark_mode)
                if not dark_logo_path.exists():
                    warnings.append(
                        f"Dark mode logo not found: {dark_logo_path}\n"
                        f"  Will use text-based logo instead."
                    )

    return warnings
