# Agentic AI in Regulated Environments

Agentic AI refers to AI systems that can autonomously plan, execute
multi-step actions, and use external tools to achieve a goal — going
beyond simple question-answering to actually performing work.

## Core components of an AI agent

A typical agent loop consists of:

1. **Perception** — receive a user instruction or trigger.
2. **Planning** — break the goal into sub-tasks.
3. **Tool selection** — choose from a registry of available tools
   (search, database query, code execution, API calls).
4. **Execution** — invoke the tool and observe the result.
5. **Reflection** — decide whether the goal is achieved or another
   iteration is needed.

## Frameworks

Common frameworks for building agents include LangChain, LangGraph,
LlamaIndex, and the Model Context Protocol (MCP). LangGraph is
particularly suited to production agents because it models the agent
loop as a stateful directed graph with explicit checkpoints, enabling
deterministic replay and human-in-the-loop approval gates.

## Considerations for regulators

Deploying agentic AI inside a regulator like the HKMA introduces
constraints that pure-play AI deployments do not face:

- **Auditability**: every prompt, retrieved document, tool call, and
  decision must be logged immutably for supervisory review.
- **Bounded autonomy**: the tool registry must be explicitly whitelisted;
  write actions should require human approval.
- **Data residency**: sensitive supervisory data should not leave
  controlled environments, often ruling out hosted LLM APIs in favour
  of private model deployments such as vLLM.
- **Evaluation gates**: regression evaluation on golden question sets
  must pass before any change to prompts, models, or retrieval is
  promoted to production.
