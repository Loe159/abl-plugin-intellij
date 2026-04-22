---
name: graphify-nav
description: "Navigate the ABL plugin knowledge graph at ~/graphify-out/ to understand architecture, find impacted components, and avoid hallucination before implementing changes."
---

# Graphify Navigation — ABL Plugin

The ABL IntelliJ plugin has a knowledge graph pre-built at `~/graphify-out/`.
**Before implementing any non-trivial change, query it to identify impacted components.**

## Files Available

```
~/graphify-out/
├── GRAPH_REPORT.md    ← community list + summary (read first)
├── graph.json         ← full graph: nodes, edges, communities
├── graph.html         ← interactive visualization (browser only)
└── manifest.json      ← file timestamps for cache invalidation
```

## Step 1 — Read the Community Overview

```bash
cat ~/graphify-out/GRAPH_REPORT.md
```

This gives you 50+ community names (e.g. "Code Completion", "Parser Facade", "Symbol Index").
Identify which communities your task touches.

## Step 2 — Find Nodes for a Concept

```bash
# Find all nodes related to "completion"
python3 -c "
import json
g = json.load(open('/root/graphify-out/graph.json'))
for n in g['nodes']:
    if 'completion' in n.get('label','').lower() or 'completion' in str(n.get('communities',[])).lower():
        print(n['id'], '|', n.get('label',''), '|', n.get('file',''))
" 2>/dev/null | head -20
```

## Step 3 — Find Edges (Dependencies) for a File

```bash
# What does AblCompletionContributor.kt depend on?
python3 -c "
import json
g = json.load(open('/root/graphify-out/graph.json'))
target = 'AblCompletionContributor'
edges = [e for e in g['edges'] if target in e.get('source','') or target in e.get('target','')]
for e in edges[:20]:
    print(e['source'], '--[', e.get('label',''), ']-->', e['target'])
"
```

## Step 4 — Update the Graph After Code Changes

```bash
cd /home/aiagent/workspace/abl-plugin-intellij
# Run graphify update (AST-only, no API cost)
# Note: requires graphify CLI or Claude Code graphify skill
# Agents: skip this step, the graph is rebuilt by the board as needed
```

## When to Use This

- **Before any implementation**: find which files you need to touch
- **When unsure about an API**: search for the class name in graph.json
- **When debugging unexpected behavior**: trace edges to find hidden dependencies
- **When adding a new feature**: check which community it belongs to and who calls it

## Quick One-liner: Community Members

```bash
python3 -c "
import json
g = json.load(open('/root/graphify-out/graph.json'))
community = 'Code Completion'   # ← change this
nodes = [n for n in g['nodes'] if community in str(n.get('communities',[]))]
for n in nodes: print(n.get('file','?'), '|', n.get('label',''))
"
```
