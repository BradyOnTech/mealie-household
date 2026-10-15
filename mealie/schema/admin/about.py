from mealie.schema._mealie import MealieModel


class AppStatistics(MealieModel):
    total_recipes: int
    total_users: int
    total_households: int
    total_groups: int
    uncategorized_recipes: int
    untagged_recipes: int


class AppInfo(MealieModel):
    production: bool
    version: str
    demo_status: bool
    allow_signup: bool
    allow_password_login: bool
    default_group_slug: str | None = None
    default_household_slug: str | None = None
    enable_oidc: bool
    oidc_redirect: bool
    oidc_provider_name: str
    token_time: int
    allowed_iframe_hosts: list[str] = []


class AppTheme(MealieModel):
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


class AppStartupInfo(MealieModel):
    is_first_login: bool
    """
    The applications best guess that a user hasn't logged in. Currently, it really
    on indicates that the 'changeme@example.com' user is still in the database. Once
    it is removed, this will always return False.
    """

    is_demo: bool


class AdminAboutInfo(AppInfo):
    versionLatest: str
    api_port: int
    api_docs: bool
    db_type: str
    db_url: str | None = None
    default_group: str
    default_household: str
    build_id: str
    recipe_scraper_version: str


class CheckAppConfig(MealieModel):
    email_ready: bool
    ldap_ready: bool
    ldap_disabled: bool
    oidc_ready: bool
    oidc_disabled: bool
    base_url_set: bool
    is_up_to_date: bool
