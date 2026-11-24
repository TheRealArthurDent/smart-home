# ha-mcp for Claude Code

Home Assistant's community MCP server, [ha-mcp](https://github.com/homeassistant-ai/ha-mcp), for prototyping
automations live (#2). It runs on the dev machine in the home network, not on the Pis: one container per Home
Assistant instance, serving streamable HTTP on `127.0.0.1` only. `.mcp.json` at the repo root points Claude Code at
them, so the servers load only when Claude Code runs in this repo.

| Server in Claude Code | Container | Port |
| --- | --- | --- |
| `ha-testbench` | `ha-mcp-testbench` | 8086 |
| `ha-raspi` | `ha-mcp-raspi` | 8087 |

## Setup

1. In each Home Assistant, create an admin user `claude` (local access only) and a long-lived token for it.
2. Copy `.env.example` to `.env` in this directory, `chmod 600 .env`, and fill in the URLs, the tokens and the
   path of the private root CA.
3. `docker compose up -d` in this directory.
4. Start Claude Code in the repo; it asks once whether to trust the servers in `.mcp.json`. `/mcp` lists them.

The image is pinned; Renovate updates it like the stack's images. To revoke access, delete the token in the profile
of the user `claude` or deactivate the user.
