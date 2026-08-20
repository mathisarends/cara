# Cara Agent Plugin API

`agent-plugin-api` is the dependency boundary between the Cara Gateway and an
installed agent plugin. It contains immutable request/context models, streamed
agent events, and structural protocols. It deliberately has no dependency on
FastAPI, Dishka, SQLModel, or the Gateway implementation.

The Gateway owns sessions and transcripts. A runner receives only the current
`AgentRunRequest`; when it needs earlier context, it reads it through the
read-only `AgentSessionReader` supplied in `AgentPluginContext`.

Plugins should import their complete Gateway-facing API from
`agent_plugin_api`, not from modules below `gateway`.
