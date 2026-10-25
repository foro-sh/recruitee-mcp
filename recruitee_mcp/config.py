import os
from dataclasses import dataclass

API_HOST = "https://api.recruitee.com"

# The same keys the foro Bridge setup form asks for.
REQUIRED = ("RECRUITEE_COMPANY_ID", "RECRUITEE_API_TOKEN")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    company_id: int
    api_token: str
    timezone: str

    @property
    def base_url(self) -> str:
        return f"{API_HOST}/c/{self.company_id}"


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ) if env is None else env
    missing = [name for name in REQUIRED if not env.get(name, "").strip()]
    if missing:
        raise ConfigError(
            "Recruitee is not connected yet. Set these secrets in the foro dashboard and "
            f"redeploy: {', '.join(missing)}. See the README's setup section."
        )

    company_id = env["RECRUITEE_COMPANY_ID"].strip()
    if not company_id.isdigit():
        raise ConfigError(f"RECRUITEE_COMPANY_ID must be a number, got {company_id!r}")

    return Settings(
        company_id=int(company_id),
        api_token=env["RECRUITEE_API_TOKEN"].strip(),
        # Recruitee wants a timezone next to every task due date.
        timezone=env.get("RECRUITEE_TIMEZONE", "").strip() or "Europe/Amsterdam",
    )
