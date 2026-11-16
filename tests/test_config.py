import pytest
from config import Config


def test_defaults(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.model_default == "qwen3.8:27b"
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


def test_model_pool_weights_default_and_parsing(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.models == ("qwen3.8:27b",) and cfg.model_weights == {"qwen3.8:27b": 1}
    cfg = Config.from_env(home=tmp_path, env={"MODEL_POOL": "qwen3:14b=3, llama3:70b=1 ,gemma4:26b"})
    assert cfg.models == ("qwen3:14b", "llama3:70b", "gemma4:26b")
    assert cfg.model_weights == {"qwen3:14b": 3, "llama3:70b": 1, "gemma4:26b": 1}


def test_per_model_thinking_overrides_the_global_flag(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={"THINK": "true", "MODEL_THINK": "llama3:70b=false,gemma4:26b=true"})
    assert cfg.think_for("llama3:70b") is False and cfg.think_for("gemma4:26b") is True
    assert cfg.think_for("qwen3:14b") is True  # not listed: global flag
    assert Config.from_env(home=tmp_path, env={}).think_for("x") is False


def test_first_read_allowance_is_a_third_of_the_context_by_default(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.first_read_allowance == int(cfg.num_ctx * 0.33)
    cfg = Config.from_env(home=tmp_path, env={"FIRST_READ_FRACTION": "0.5", "NUM_CTX": "1000"})
    assert cfg.first_read_allowance == 500
