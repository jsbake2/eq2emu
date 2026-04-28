# Bot personalities — design

LLM-driven banter for mercenary bots. The goal is bots that feel like
characters in a small group of friends, not animatronic spell-casters —
sarcastic, in-character, occasionally chiming in on player chat without
breaking immersion.

This doc captures the design decisions while the ground-level bot AI
work (recategorization, prepull, healer-mode, cures) takes priority.
The implementation is on the shelf; pick it back up by reading this
plus `personas.md` and following the phases below.

## Scope decisions

- **Banter, not reactions.** No "I'm at 5% HP!" panic chatter, no
  "DING gratz!" auto-responses. Just ambient personality.
- **Reading group chat.** When a player or another bot says something
  in `/g`, a bot may reply in character. Not every bot replies, not
  every line earns a reply — see "When a bot speaks" below.
- **Idle banter.** When the group is in a town/zone idle for a while,
  bots occasionally toss in a one-liner consistent with persona +
  current zone.
- **No rate limit on chat-driven replies.** Bots respond as the chat
  flows. The probabilistic gate (only some bots reply, only some lines
  trigger) is the volume control.
- **Rate limit on idle banter.** ~5-10 minutes between idle quips per
  bot, jittered so they don't all chime at once.

## Backend choice — Ollama vs hosted free tier

Two viable options. The design doesn't lock either in; both expose
HTTP APIs the C++ hook can POST to with the same envelope.

### Option A — Ollama container (local)

Add an `ollama` service to `docker-compose.override.yaml`. Pull a
small instruct-tuned model (`llama3.2:3b` or `phi-3:mini` are plenty
for "1-3 sentence quip in character").

- ✓ Zero recurring cost, no API keys, no rate limits, private.
- ✓ Survives losing the friends-server's internet connection.
- ✗ Latency: 2-5s per reply on CPU on this homelab. Acceptable for
  ambient banter; not for snappy reactions (which we explicitly don't
  want anyway).
- ✗ Adds memory pressure to the homelab — a 3B-param model wants
  ~4-6GB RAM warm. Currently the host has headroom.
- ✗ Can't easily batch — each bot reply is a sequential generate.

### Option B — Free-tier hosted

The user noted: hosted models are usually pay-per-token. There are
exceptions worth checking:

- **Cloudflare Workers AI** — free tier with a daily token allowance,
  no card on file required. Many open models available (`@cf/meta/
  llama-3.1-8b-instruct`, `@cf/microsoft/phi-2`, etc.) Reasonable
  latency (~1s).
- **Groq** — free tier, very fast inference (sub-second), 30
  requests/minute on llama-3.1-8b. Rate limit could bite during a
  raid pull where 6 bots are bantering.
- **Google AI Studio (Gemini)** — has a free tier on
  `gemini-flash-2.x` with daily quotas.
- **Hugging Face Inference Endpoints** — free tier exists but rate-
  limited and historically flaky.

Tradeoff: hosted is faster but has hard request-rate ceilings that
are easy to hit with 6 bots × active group. Ollama is slower but
unmetered.

**Recommendation for first cut:** Ollama with `llama3.2:3b` because
of the unmetered nature. If the latency feels bad in practice, swap
the backend by changing one URL in the C++ hook — the prompts and
persona-stitching don't depend on which engine answers.

## Architecture

```
   ┌────────────┐                  ┌──────────────┐
   │  player    │  /g msg          │              │
   │  client    │ ───────────────▶ │  WorldServer │
   └────────────┘                  │              │
                                   │ ┌──────────┐ │
                                   │ │ChatHooks │ │   POST /api/generate
                                   │ │ (new C++)│─┼──────────────────────┐
                                   │ └──────────┘ │                      │
                                   └──────────────┘                      │
                                          ▲                              ▼
                                          │                       ┌────────────┐
                                          │  back as MessageGroup │   Ollama   │
                                          └───────────────────────│  container │
                                                                  └────────────┘
```

A new file `WorldServer/Bots/BotChat.cpp` (or similar) intercepts:
- `Client::SendChannelMessage` when the channel is the player's group
- A periodic idle tick on each bot (the brain already ticks)

For each event, decide whether to fire (probabilistic), pick a bot,
build the prompt (persona + recent group chat context + event), POST
to Ollama, and on response call `Bot::MessageGroup(reply)`.

Async: the C++ HTTP call must not block the brain tick. Easiest path
is `std::async` + a result queue the brain drains on its next tick.

## Persona system

Each bot gets a persona derived from its **race × class × name**.
Race contributes worldview; class contributes role-flavor; name is
the speaker handle.

Personas live in `docs/bot-personalities/personas.md` and get loaded
into a new DB table:

```sql
CREATE TABLE bot_persona (
    bot_id INT UNSIGNED PRIMARY KEY,
    persona_prompt TEXT NOT NULL,
    speech_style VARCHAR(64),       -- e.g. "gruff", "scholarly"
    chime_in_chance FLOAT DEFAULT 0.15,  -- baseline probability per chat line
    idle_minutes_min INT DEFAULT 5,
    idle_minutes_max INT DEFAULT 10,
    FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE CASCADE
);
```

The `personas.md` file is the authored source of truth; a script
seeds the DB from it.

## When a bot speaks

**Chat-driven reply path:**
1. Player or bot says X in /g.
2. For each living bot in the group, roll `chime_in_chance`
   (default 15%, tunable per bot in DB). Cap at 1 reply per chat line
   per group (don't let two bots step on each other).
3. If a bot wins the roll, build prompt:
   - System: persona_prompt + speaker_name + zone_context + last 5
     group chat lines (rolling buffer).
   - User: just spoke "X". Reply in character in 1-2 sentences. Stay
     in your speech_style. Skip the reply if the line doesn't earn
     one (return empty).
4. POST to LLM. On response, `Bot::MessageGroup(reply)` if
   non-empty, otherwise drop silently.

**Idle path:**
1. Each bot's brain tick checks: am I in a safe zone, group not in
   combat, has it been at least `idle_minutes_min` since I last
   spoke?
2. If yes, roll low probability (e.g. 5%/tick at 1 tick/min cadence,
   yielding a reply every 5-10 min on average).
3. Build idle prompt: persona + zone + "say something in character
   about the moment, the location, your group, or your mood."
4. POST + MessageGroup as above.

## Phases

1. **Persona library + design.** This doc. ✓
2. **DB scaffolding.** `bot_persona` table + Python loader that
   reads `personas.md` and seeds the DB.
3. **Ollama container.** Add to compose override; verify `curl
   http://ollama:11434/api/generate` from inside `eq2emu-server-1`.
4. **Async HTTP client in C++.** Tiny libcurl wrapper or use
   existing `axios`-style helper if the codebase has one.
5. **Chat hook (chat-driven).** Intercept group chat in
   `Client::SendChannelMessage`; gate by chime_in_chance; build
   prompt; queue async; on result `MessageGroup`.
6. **Idle hook.** Per-bot brain tick path.
7. **Live tuning.** Ride along for a session, watch for: bots
   talking over each other, off-character drift, latency spikes.

Skip anything that requires real-time reactions — that's explicitly
out of scope.

## Why not just hard-code lines

Pre-rendered line tables (e.g. 50 quips per persona) work but feel
loop-y after the first couple of evenings. The point of the LLM is
that it can pull the *zone name*, *recent chat context*, *whether
you just zoned*, *who in the group is a different race*, etc. into a
dynamic line. A defiler in Antonica will rasp something different
than the same defiler in Greater Faydark — that's the unique-feel
the user is after.

If the LLM stack proves too operationally heavy, the fallback is
exactly that hard-coded line table — same DB schema, same hook
points, just `random.choice(persona.lines)` instead of `llm.generate`.
