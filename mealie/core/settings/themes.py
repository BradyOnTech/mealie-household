from pydantic_settings import BaseSettings, SettingsConfigDict


class Theme(BaseSettings):
    light_primary: str = "#211C16"
    light_accent: str = "#B3432A"
    light_secondary: str = "#5D7253"
    light_success: str = "#4F7A4A"
    light_info: str = "#3D6585"
    light_warning: str = "#A8701D"
    light_error: str = "#9F2D2D"

    dark_primary: str = "#F0E8DA"
    dark_accent: str = "#E57B5D"
    dark_secondary: str = "#9DB28E"
    dark_success: str = "#8FB386"
    dark_info: str = "#8DB4D4"
    dark_warning: str = "#E0A84F"
    dark_error: str = "#E2675F"
    model_config = SettingsConfigDict(env_prefix="theme_", extra="allow")
