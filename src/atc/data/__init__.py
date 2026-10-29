from atc.config import get_settings


def default_data():
    return get_settings().xplane_dir / "Resources" / "default data"
