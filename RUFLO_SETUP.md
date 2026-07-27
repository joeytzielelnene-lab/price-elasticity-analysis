# Ruflo Setup Guide

Ruflo v3.6.27 — AI Agent Orchestration Platform by ruv.io

---

## Prerequisites

- Node.js installed
- `ruflo` installed globally via npm

```bash
npm install -g ruflo
# verify
ruflo --version
```

---

## Step 1 — Initialize Ruflo in Your Project

Navigate to your project directory and run:

```bash
npx ruflo init
```

This creates:

| Path | Contents |
|------|----------|
| `.claude/` | 98 agents, 30 skills, 10 commands, settings.json, 7 hooks |
| `.claude-flow/` | config.yaml, logs/, sessions/, data/ |
| `.mcp.json` | MCP server config for Claude Code integration |
| `.swarm/` | Created later by memory init |

---

## Step 2 — Start the Background Daemon

```bash
ruflo daemon start
```

Starts background workers needed for agent coordination.

- Logs written to `.claude-flow/daemon.log`
- To stop: `ruflo daemon stop`

---

## Step 3 — Initialize the Memory Database

```bash
ruflo memory init
```

Sets up the hybrid memory backend with:

- Vector Embeddings
- Pattern Learning
- Temporal Decay
- HNSW Indexing (150x–12,500x faster search)
- Migration Tracking

Database is stored at `.swarm/memory.db`.

---

## Step 4 — Initialize the Swarm

```bash
ruflo swarm init
```

Creates the agent coordination layer:

| Property | Value |
|----------|-------|
| Topology | hierarchical-mesh |
| Max Agents | 15 |
| Auto Scale | Enabled |
| Protocol | message-bus |

---

## Step 5 — (Optional) Start the MCP Server

Enables Claude Code to connect to Ruflo via the MCP protocol:

```bash
ruflo mcp start
```

MCP config is already in `.mcp.json` — Claude Code picks it up automatically when the server is running.

---

## All-in-One Command

To run Steps 2–4 in one shot:

```bash
ruflo init --start-all
```

---

## Check System Status

> **Note:** `ruflo status` always shows STOPPED — known bug. The MCP server runs in stdio mode (for Claude Code), and `ruflo status` expects an HTTP connection it can never get. Use the commands below instead.

```bash
# Daemon (background workers)
ruflo daemon status

# Swarm (replace with your swarm ID)
ruflo swarm status <swarm-id>

# Memory
ruflo memory stats

# Full diagnostics
ruflo doctor
```

---

## Useful Commands Reference

| Command | What it does |
|---------|-------------|
| `ruflo daemon start` | Start background workers |
| `ruflo daemon stop` | Stop background workers |
| `ruflo memory init` | Initialize memory database |
| `ruflo memory search -q "query"` | Semantic search across memory |
| `ruflo swarm init` | Initialize agent swarm |
| `ruflo swarm init --v3-mode` | Initialize with V3 enhancements |
| `ruflo agent spawn -t coder` | Spawn a specific agent type |
| `ruflo mcp start` | Start MCP server |
| `ruflo status` | Show full system status |
| `ruflo doctor` | Run diagnostics |
| `ruflo config list` | List all config values |
| `ruflo daemon stop` | Stop all background processes |

---

## Teardown / Cleanup

```bash
ruflo daemon stop
ruflo cleanup
```

`cleanup` removes all artifacts created by ruflo in the project directory.
