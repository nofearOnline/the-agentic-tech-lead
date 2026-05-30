# the-agentic-tech-lead

Demo repository for **The Agentic Tech Lead** presentation.

The repo is split into two pieces: the *thing being reviewed*, and the
*thing doing the reviewing*. Each version of the reviewer lives in its own
folder so the talk can walk the audience from "just call the LLM" all the
way to a real agentic reviewer.

## Layout

```
the-agentic-tech-lead/
├── payments-service/        ← the demo target (TypeScript + Express)
│   └── ...                    A small payments service with three
│                              intentionally-flawed PRs opened against it.
└── pr-agent/                ← the reviewer, in versions
    ├── README.md
    └── v1_single_shot/        Diff in, review out. One LLM call.
        └── ...
```

## payments-service

A small, intentionally-clean TypeScript + Express service that processes
card transactions through a fake gateway. See
[`payments-service/README.md`](payments-service/README.md) for endpoints,
layout, and how to run it.

Three deliberately-bad PRs are open against it on GitHub, escalating in
size and in the variety of problems they contain (KISS / quality, then
DRY / performance, then security / standards).

## pr-agent

Successive versions of a PR-reviewing agent that all target the
`payments-service` PRs. See [`pr-agent/README.md`](pr-agent/README.md) for
the version index.
