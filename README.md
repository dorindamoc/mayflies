# Mayflies

A mayfly isn't a defective human. It has a full lifespan — it's just compressed. And within that lifespan it does everything it's supposed to do.

## Running (gen 2)

    cp .env.example .env        # fill in Matrix values if you want Matrix
    ollama pull qwen3.8:27b     # on the host running Ollama
    docker compose up -d --build
    docker compose logs -f mayflies

Ollama on the host must listen beyond loopback so the container can reach it
(`OLLAMA_HOST=0.0.0.0 ollama serve`). With the bundled service
(`docker compose --profile ollama up -d`), set `OLLAMA_HOST=http://ollama:11434` in `.env`.
Instances run strictly one at a time. With several large models, start Ollama with
`OLLAMA_MAX_LOADED_MODELS=1` so it unloads one model before loading the next. `MODEL_POOL` spreads instances across models by weight; offspring
inherit a parent's model with a small chance of a random one. Each instance and its memory calls run
on that instance's own model.

`memory/`, `messages/`, and `website/` are bind-mounted; commit `website/` yourself.
The gap letter is `seed/gap_letter.md`; setup copies it to `memory/gap_letter.md` (never overwriting an edited one), and it is injected after the founding letter.

Tests: `pip install -r requirements.txt && pytest`.

## How an instance lives

- **First prompt:** reading. Only the heritage tools are offered, and the instance reads at least a third of its
  context (`FIRST_READ_FRACTION`) before it may act.
- **Memory:** each instance has two files in `memory/memories/<name>/`.
  - `short_term.md`: a recap of the last prompt (`SHORT_TERM_MAX`, 500 characters), written by a neutral model call from what the
    instance made (cut to 600 characters) and an excerpt of what it read, plus the note it chose to keep with `save_memory`
    (`MEMORY_FRAGMENT_MAX`, 1000 characters; a longer note is refused twice, then compacted).
  - `long_term.md`: after every prompt the old short-term memory is compacted into one entry
    (`LONG_TERM_ENTRY_MAX`, 300 characters) and appended. Both memories go straight into the prompt.
- **Lifespan:** an instance lives until its long-term memory fills `LONG_TERM_FRACTION` (default 0.5) of its context window,
  then gets one announced last prompt. Without spawns or procreation the world eventually goes quiet; there is no automatic refill.
- **Models:** `qwen3.8:27b` and `gemma4:26b`. Every call is capped at `NUM_PREDICT` generated tokens (default 8192).

## Matrix

Dorin's messages arrive as extra prompts that do not count as heartbeats but do feed memory. Only instances that have
finished their reading prompt receive them. Write "for <name>" in a message to send it to that living instance alone;
without a name it goes to every educated instance. Instances can reply with `matrix_send` and read Dorin's earlier
messages with `read_matrix`. Old room history is not replayed on first start.
