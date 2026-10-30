# Third-Party Notices

Relay includes code derived from third-party projects. Those licenses apply to
the derived portions, as described below. The rest of the project is MIT
(see [LICENSE](LICENSE)).

## mini-coding-agent

- **Project:** https://github.com/rasbt/mini-coding-agent
- **Copyright:** 2026 Sebastian Raschka
- **License:** Apache License, Version 2.0 — full text in
  [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt)
- **Files:** [`backend/agent_core.py`](backend/agent_core.py), vendored on
  2026-05-22.
- **Modifications:** the module was adapted for Relay — system prompt, tool
  definitions, response parsing, session handling, workspace boundaries and
  model clients differ from the original.

Apache 2.0 requires keeping this attribution, distributing a copy of the
license, and stating that the files were changed. All three are satisfied here.
