# Cara — Product and Technical Vision

**Cara should become a persistent personal agent that understands my context, interacts naturally, and reliably acts across my digital and physical environment.**

Cara should feel like one coherent assistant available through voice, text, and different devices. She maintains continuity across conversations, remembers relevant information, and follows through on delegated tasks.

This vision defines the intended behavior and technical qualities of a fresh implementation. The existing repository provides useful experience and reference behavior. The technology stack, architecture, protocols, and integration mechanisms remain open design decisions.

**Rooms and their devices form a central part of Cara's understanding of her environment.** Each room represents a physical place with associated devices and capabilities: microphones, speakers, music playback devices, lights, and potentially displays or other equipment.

When I speak through a particular microphone, Cara can resolve which room the interaction originates from. That room provides the default context for interpreting my request and choosing where to respond or act.

For example:

- "Play some music" selects an appropriate music source and plays it through the speakers associated with the current room.
- "Turn it down" refers to the relevant playback in that room.
- "Play jazz in the living room" explicitly targets the living room.
- "What's the weather tomorrow?" produces a spoken response through a suitable speaker in the room where I asked.
- When I continue a conversation through a microphone in another room, Cara carries the relevant conversation context into that interaction.

This is the intended meaning of **Cara following me through the house**: the active interaction moves between rooms while the assistant maintains continuity.

Technically, Cara needs to resolve the relationship between an input device, its room, available output devices, and the capabilities required for an action. Explicit destinations take precedence over inferred defaults. The source microphone establishes the interaction's room context; identifying the person speaking is a separate concern.

**Music selection, playback location, and conversational audio should work together.** Spotify represents a potential source of music and account-specific content. Sonos represents playback devices and their physical placement. Cara should understand the user's intent across those capabilities.

A request such as "Play my focus playlist here" combines a personal content reference, a music service, the current room, and a suitable playback destination.

Voice interaction also needs to coexist with music. Cara should manage audio focus so that I can speak and hear her clearly, then restore the appropriate playback state. Restoration should respect any changes I made during the conversation.

**Tools give Cara grounded knowledge and practical abilities.** The following capability areas describe the intended scope. Some already have partial implementations in the repository; others extend the ambition.

| Capability | Intended behavior |
| --- | --- |
| **Spotify and music services** | Find tracks, artists, albums, and playlists; resolve personal music references; initiate or control supported playback. |
| **Sonos and room audio** | Select playback destinations, inspect playback state, control volume, and coordinate music with conversational audio. |
| **Web search and retrieval** | Find current information, inspect relevant sources, and answer with traceable evidence. |
| **Weather** | Retrieve current conditions and forecasts for an explicit or contextually resolved location, with clear dates and units. |
| **Geolocation and places** | Resolve named places, configured home locations, and available device location into usable geographic context. |
| **Time and scheduling** | Obtain authoritative current time, handle time zones and daylight saving changes, and interpret relative dates and times. |
| **Reminders, alarms, and routines** | Create, inspect, change, cancel, and deliver scheduled actions through an appropriate room or channel. |
| **Lighting and environmental feedback** | Control supported devices and provide understandable feedback about listening, processing, and speaking. |
| **Files and workspace operations** | Read, create, and organize information, and perform authorized computational tasks in a controlled workspace. |

These capabilities should compose naturally. "Every weekday morning, tell me today's weather here and then play my morning playlist" combines scheduling, geographic context, weather retrieval, spoken delivery, and music playback.

Geographic location and room location have different meanings. A microphone can establish that I am interacting from the kitchen; a configured home address or another location source establishes which city's weather is relevant. Location information should retain its source, precision, and freshness.

**Tool execution should have clear, inspectable contracts.** Cara needs enough information to understand what a capability does, which inputs it requires, which context it uses, and what its result means.

Useful technical properties include validated inputs, structured results where appropriate, explicit errors, bounded execution, and cancellation where supported. The system should distinguish between an accepted command and a confirmed outcome.

When a device becomes unreachable after receiving a command, Cara should preserve the uncertainty about whether it executed. Retry behavior should account for the action's effects: setting an absolute volume and starting another playback session have different consequences.

The choice of SDKs, direct APIs, tool protocols, or local adapters can follow from the eventual design.

**Conversation context, memory, and task state should support different lifetimes.** Conversation context supports the current exchange. Memory preserves useful facts, preferences, and decisions. Task state records commitments and ongoing work.

A room change, a closed client, or a restarted process should preserve the information needed to continue an ongoing task. Context sharing should remain relevant to the current interaction and respect who may receive the information.

Memory should be inspectable and correctable. Cara should distinguish explicit user statements from inferred preferences and temporary observations.

**Delegated work should remain understandable and controllable.** Cara should be able to plan a task, use tools, inspect results, wait for external conditions, and continue later. She should also coordinate specialized subagents—for example, a coding agent that investigates a repository, implements changes, runs relevant checks, and returns reviewable results.

Cara should define each subagent's objective, provide relevant context and appropriate permissions, track progress, and coordinate dependencies. Independent tasks may run in parallel. She remains responsible for evaluating their outputs and integrating them into the overall result.

I should be able to ask what Cara and her subagents are doing, inspect intermediate results, change priorities, redirect work, or cancel outstanding tasks. Changes to the overall assignment should propagate to affected subagents. Progress reporting should distinguish completed work, ongoing activity, blockers, and decisions requiring my input.

Scheduled behavior needs explicit semantics for timing, delivery destination, and missed execution. A reminder intended for a room that is temporarily offline should follow a deliberate delivery policy.

Cara's initiative should reflect my instructions and preferences, including when to notify me, which channel to use, and when an interruption is appropriate.

**Reliability should be measured through complete user experiences.** Important measures include response latency, interruption behavior, correct room and device selection, successful task completion, and recovery after connection loss.

The system should make it possible to trace how an input became a room context, how a destination was selected, which tools executed, and what outcome was observed. Repeated failures and user corrections should become evaluation scenarios. Changes to skills or behavior should be versioned, evaluated, and reversible.

An early implementation should demonstrate a small set of complete experiences:

1. Speak through a room's microphone and receive the answer through that room's speaker.
2. Select music through natural language and play it in the inferred or explicitly named room.
3. Interrupt Cara during playback and continue the conversation naturally.
4. Continue a conversation from another room with the relevant context intact.
5. Schedule a room-targeted reminder and observe defined behavior through a temporary outage.

**Guidance for the implementing agent:** Design toward these experiences and technical properties. Choose architecture and technology based on evidence from working scenarios. Build in complete, usable increments, with particular attention to room context, device routing, conversational continuity, and verifiable outcomes.
