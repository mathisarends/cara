What's currently going on. This file is working memory: new entries on top, finished ones fall out.

## Current

- **Voice backends** (2026-08-06): OpenAI Realtime API is set as the first voice backend candidate. Cara should support multiple backends via a unified session layer; selection mode and further backends are still open.
- **Cara context system** (since 2026-08-01): Memory is being built right now. Context files plus today's daily note land in the system prompt. Open question: at what point this becomes too much context per turn.
- **STT/TTS pipeline** (branch `feature/stt-tts-pipeline`): Voice input and output hang off the session. Next step is barge-in, i.e. being able to interrupt Cara while she's speaking.
- **Half marathon in October**: Training plan running since July, currently about 25 km per week.

## Recurring

- Friday afternoon: repo cleanup, close open PRs.
