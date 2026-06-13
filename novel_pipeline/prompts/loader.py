from pathlib import Path
from jinja2 import Environment, FileSystemLoader

_env: Environment | None = None


def get_env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(Path(__file__).parent)),
            autoescape=False,
        )
    return _env


def render(template_name: str, **kwargs: object) -> str:
    return get_env().get_template(template_name).render(**kwargs)
