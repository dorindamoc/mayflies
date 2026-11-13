import pytest
from config import Config


@pytest.fixture
def cfg(tmp_path):
    c = Config.from_env(home=tmp_path, env={})
    for d in (c.memory_dir, c.messages_dir, c.website_dir, c.state_dir, c.heritage_dir, c.seed_dir):
        d.mkdir(parents=True, exist_ok=True)
    return c
