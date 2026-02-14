from pathlib import Path
import pytest
import yaml


ROOT = Path(__file__).parent.parent


def pytest_addoption(parser):
    parser.addoption(
        "--client-dir",
        default=str(ROOT / "clients" / "cchmc"),
        help="Path to client directory containing config.yaml and data/reference/",
    )


@pytest.fixture(scope="session")
def client_dir(request):
    return Path(request.config.getoption("--client-dir")).resolve()


@pytest.fixture(scope="session")
def client_config(client_dir):
    config_path = client_dir / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def refinement(client_dir, client_config):
    path = client_dir / client_config["paths"]["refinement_rules"]
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def sc_mapping(client_dir, client_config):
    path = client_dir / client_config["paths"]["sc_mapping"]
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def keyword_rules(client_dir, client_config):
    path = client_dir / client_config["paths"]["keyword_rules"]
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def taxonomy_keys(client_dir, client_config):
    import pandas as pd
    path = client_dir / client_config["paths"]["taxonomy"]
    df = pd.read_excel(path)
    return set(df["Key"].dropna().astype(str))


@pytest.fixture(scope="session")
def valid_sc_codes(sc_mapping):
    return set(str(k).strip() for k in sc_mapping.get("mappings", {}).keys())
