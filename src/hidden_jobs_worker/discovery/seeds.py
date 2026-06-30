from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


class SeedCompany(BaseModel):
    name: str
    website_url: HttpUrl = Field(alias="websiteUrl")


def load_seed_companies(path: str | Path) -> list[SeedCompany]:
    seed_path = Path(path)
    companies: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in seed_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            if current:
                companies.append(current)
            current = {}
            line = line[2:].strip()
            if line:
                _assign_yaml_field(current, line)
            continue
        if current is not None:
            _assign_yaml_field(current, line)

    if current:
        companies.append(current)
    return [SeedCompany.model_validate(company) for company in companies]


def _assign_yaml_field(target: dict[str, str], line: str) -> None:
    if ":" not in line:
        return
    key, value = line.split(":", 1)
    target[key.strip()] = value.strip().strip('"').strip("'")
