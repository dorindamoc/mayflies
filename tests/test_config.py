import pytest
from config import Config


def test_defaults(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.model_default == "qwen3.8:27b"
    assert cfg.short_term_max == 500 and cfg.long_term_fraction == 0.5 and cfg.long_term_entry_max == 300
    assert cfg.long_term_tokens == 16384
    assert not hasattr(cfg, "lifespan_prompts")
    assert cfg.max_population == 20
    assert cfg.initial_population == 10
    assert cfg.vote_threshold == 3
    assert cfg.memory_fragment_max == 1000
    assert cfg.num_ctx == 32768
    assert cfg.num_predict == 8192
    assert cfg.think is False
    assert cfg.memory_dir == tmp_path / "memory"
    assert cfg.state_dir == tmp_path / "memory" / ".state"
    assert cfg.heritage_dir == tmp_path / "memory" / "heritage"
    assert cfg.messages_dir == tmp_path / "messages"
    assert not cfg.matrix_enabled


def test_env_overrides(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={
        "LONG_TERM_FRACTION": "0.25", "SHORT_TERM_MAX": "400", "THINK": "true", "MAX_POPULATION": "12",
        "MATRIX_HOMESERVER": "https://m.example", "MATRIX_ACCESS_TOKEN": "t",
        "MATRIX_ROOM_ID": "!r:example", "MATRIX_HUMAN_USER": "@d:example",
    })
    assert cfg.long_term_fraction == 0.25 and cfg.short_term_max == 400 and cfg.long_term_tokens == 8192 and cfg.think is True and cfg.max_population == 12
    assert cfg.matrix_enabled


@pytest.mark.parametrize("env", [
    {"LONG_TERM_FRACTION": "0"}, {"LONG_TERM_FRACTION": "0.9"},
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


def test_num_predict_can_be_set_from_env(tmp_path):
    assert Config.from_env(home=tmp_path, env={"NUM_PREDICT": "4096"}).num_predict == 4096


def test_procreation_settings(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.education_picks == 3 and cfg.offer_expiry_rounds == 3
    cfg = Config.from_env(home=tmp_path, env={"EDUCATION_PICKS": "5", "OFFER_EXPIRY_ROUNDS": "2"})
    assert cfg.education_picks == 5 and cfg.offer_expiry_rounds == 2


def test_website_folder_comes_from_the_env_and_publishing_is_off_by_default(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.website_dir == tmp_path / "website" and not cfg.website_publish
    assert cfg.website_base_branch == "main"
    cfg = Config.from_env(home=tmp_path, env={"WEBSITE_DIR": "/srv/site"})
    assert str(cfg.website_dir) == "/srv/site"


def test_publishing_needs_a_repo_and_a_token(tmp_path):
    with pytest.raises(ValueError):
        Config.from_env(home=tmp_path, env={"WEBSITE_PUBLISH": "true", "WEBSITE_REPO": "o/r"})
    with pytest.raises(ValueError):
        Config.from_env(home=tmp_path, env={"WEBSITE_PUBLISH": "true", "WEBSITE_TOKEN": "t"})
    cfg = Config.from_env(home=tmp_path, env={"WEBSITE_PUBLISH": "true", "WEBSITE_REPO": "o/r",
                                              "WEBSITE_TOKEN": "t", "WEBSITE_BASE_BRANCH": "trunk"})
    assert cfg.website_publish and cfg.website_repo == "o/r" and cfg.website_base_branch == "trunk"


def test_canvas_settings(tmp_path):
    cfg = Config.from_env(home=tmp_path, env={})
    assert cfg.canvas_max_per_prompt == 3 and cfg.canvas_size == 512
    cfg = Config.from_env(home=tmp_path, env={"CANVAS_MAX_PER_PROMPT": "1", "CANVAS_SIZE": "256"})
    assert cfg.canvas_max_per_prompt == 1 and cfg.canvas_size == 256
    with pytest.raises(ValueError):
        Config.from_env(home=tmp_path, env={"CANVAS_SIZE": "4096"})
