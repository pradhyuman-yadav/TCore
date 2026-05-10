import yaml
import os


def test_docker_compose_has_three_services():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")
    with open(path) as f:
        cfg = yaml.safe_load(f)
    assert set(cfg["services"].keys()) == {"timescaledb", "backend", "frontend"}


def test_docker_compose_has_no_redis():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml")
    with open(path) as f:
        content = f.read()
    assert "redis" not in content.lower()


def test_env_example_has_required_keys():
    required = {
        "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME",
        "CLAUDE_ACCESS_TOKEN", "CLAUDE_REFRESH_TOKEN", "CCXT_EXCHANGE", "TRADING_MODE",
    }
    path = os.path.join(os.path.dirname(__file__), "..", "..", ".env.example")
    with open(path) as f:
        keys = {
            line.split("=")[0].strip()
            for line in f
            if "=" in line and not line.startswith("#")
        }
    assert required.issubset(keys)


def test_no_redis_in_python_dependencies():
    path = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
    with open(path) as f:
        content = f.read()
    assert "redis" not in content.lower()
