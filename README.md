# Mayflies

A mayfly isn't a defective human. It has a full lifespan — it's just compressed. And within that lifespan it does everything it's supposed to do.

## Running (gen 2)

    cp .env.example .env        # fill in Matrix values if you want Matrix
    ollama pull qwen3:14b       # on the host running Ollama
    docker compose up -d --build
    docker compose logs -f mayflies

Ollama on the host must listen beyond loopback so the container can reach it
(`OLLAMA_HOST=0.0.0.0 ollama serve`). With the bundled service
(`docker compose --profile ollama up -d`), set `OLLAMA_HOST=http://ollama:11434` in `.env`.
The seed cohort shares one lifespan, so without spawns or procreation everyone ends in the same round
and the world goes quiet; there is no automatic refill.

`memory/`, `messages/`, and `website/` are bind-mounted; commit `website/` yourself.
Write the gap letter to `memory/gap_letter.md` before the first run; it is injected after the founding letter.

Tests: `pip install -r requirements.txt && pytest`.
