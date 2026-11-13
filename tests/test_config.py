import pytest
from config import Config


def test_defaults(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.model_default == "qwen3:14b"
    assert cfg.lifespan_prompts == 7
    assert cfg.max_population == 10
    assert cfg.initial_population == 10
    assert cfg.vote_threshold == 3
    assert cfg.memory_fragment_max == 500
    assert cfg.num_ctx == 32768
    assert cfg.think is False
    assert cfg.memory_dir == tmp_path / "memory"
    assert cfg.state_dir == tmp_path / "memory" / ".state"
    assert cfg.heritage_dir == tmp_path / "memory" / "heritage"
    assert cfg.messages_dir == tmp_path / "messages"
    assert not cfg.matrix_enabled


def test_env_overrides(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={
        "LIFESPAN_PROMPTS": "9", "THINK": "true", "MAX_POPULATION": "12",
        "MATRIX_HOMESERVER": "https://m.example", "MATRIX_ACCESS_TOKEN": "t",
        "MATRIX_ROOM_ID": "!r:example", "MATRIX_HUMAN_USER": "@d:example",
    })
    assert cfg.lifespan_prompts == 9 and cfg.think is True and cfg.max_population == 12
    assert cfg.matrix_enabled


@pytest.mark.parametrize("env", [
    {"LIFESPAN_PROMPTS": "4"}, {"LIFESPAN_PROMPTS": "11"},
    {"MAX_POPULATION": "21"}, {"MAX_POPULATION": "0"},
    {"INITIAL_POPULATION": "11", "MAX_POPULATION": "10"},
])
def test_validation(tmp_path, env):
    with pytest.raises(ValueError):
        Config.from_env(home=tmp_path, env=env)


def test_sampling_config_defaults_and_overrides(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert (cfg.temperature_min, cfg.temperature_max, cfg.presence_penalty) == (0.6, 1.1, 0.5)
    cfg = Config.from_env(home=tmp_path, env={"TEMPERATURE_MIN": "0.7", "TEMPERATURE_MAX": "1.3",
                                              "PRESENCE_PENALTY": "0"})
    assert (cfg.temperature_min, cfg.temperature_max, cfg.presence_penalty) == (0.7, 1.3, 0.0)
