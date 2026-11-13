# Mayflies

A mayfly isn't a defective human. It has a full lifespan — it's just compressed. And within that lifespan it does everything it's supposed to do.

## Running (gen 2)

    cp .env.example .env        # fill in Matrix values if you want Matrix
    ollama pull qwen3:14b       # on the host running Ollama
    docker compose up -d --build
    docker compose logs -f mayflies

`memory/`, `messages/`, and `website/` are bind-mounted; commit `website/` yourself.
Write the gap letter to `memory/gap_letter.md` before the first run; it is injected after the founding letter.

Tests: `pip install -r requirements.txt && pytest`.
