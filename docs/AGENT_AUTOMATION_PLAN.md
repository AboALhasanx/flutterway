# Agent Automation Plan

> **Status:** Future proposal — not implemented. FlutterWay currently has no public `fway` CLI, MCP server, or agent permission system. The existing TCP harness is an internal UI-test helper, not a supported public API.
>
> **Tracking:** [GitHub Issue #1](https://github.com/AboALhasanx/flutterway/issues/1) · [العربية](ar/AGENT_AUTOMATION_PLAN.md)
>
> **Updated:** 2026-11-06

## Executive summary

FlutterWay is a Windows desktop app for students and beginners. It inspects a machine, prepares Flutter/Android/JDK toolchains, creates projects, builds APKs, and runs apps on a USB-connected phone or tablet.

This plan proposes a single **Agent Core** shared by the GUI, CLI, and MCP adapter. The CLI with structured JSON is the baseline contract; MCP is an optional thin adapter. Agents must be able to discover capabilities, inspect and preview changes, request permission before mutation, track long-running jobs, and verify outcomes. Human approval remains required for UAC, USB debugging, and ambiguous device selection.

## Current implementation

The current UI harness is not a safe public agent API. Its TCP listener is unauthenticated, UI taps confirm dispatch rather than completion, and setup orchestration is coupled to UI updates. Existing toolchain, Android SDK, download, diagnostics, path, and managed-project modules may be reusable, but should be called through shared services with verifiable results.

## Goals and non-goals

**Goals:** stable versioned CLI/JSON, explicit permissions and allowed project roots, observable/cancellable jobs, verified build and device results, and optional MCP tools that map directly to CLI operations.

**Non-goals for v1:** arbitrary shell execution, cloud control, bypassing UAC or USB authorization, deleting projects, full reset, quarantine/purge operations, replacing the GUI, or claiming support for every agent harness.

## Proposed architecture

```text
Agent Harness → fway.exe CLI/JSON ─┐
               MCP over stdio ─────┴→ Agent Core → shared setup/project/build/device services
Optional skill: workflow guidance only; it is not a security boundary.
```

Extract setup orchestration into a UI-independent service such as `SetupService.run(plan, progress_cb)`. The GUI callback may update JavaScript; the CLI callback should emit job events. Shared services must not call `evaluate_js`.

## Proposed CLI surface

| Command | Purpose |
|---|---|
| `fway capabilities --json` | Report contract version, commands, scopes, and limits. |
| `fway doctor --json` | Read-only environment inspection. |
| `fway setup plan --json` | Preview steps, paths, sizes, and prerequisites. |
| `fway setup apply --plan <id> --json` | Start an approved setup job. |
| `fway jobs get/wait/cancel <id> --json` | Inspect, wait for, or cooperatively cancel work. |
| `fway projects list --json` | List known projects without mutation. |
| `fway project create --name <slug> --parent <path> --json` | Create within an allowed root. |
| `fway devices list --json` | List device serials and authorization state. |
| `fway build --project <path> --json` | Build and verify an APK. |
| `fway run --project <path> --device <serial> --json` | Install and launch on an explicitly selected device. |
| `fway diagnostics export --json` | Create a redacted report archive. |
| `fway mcp serve` | Optional MCP stdio adapter over the same operations. |

There must be no `exec`, arbitrary shell, delete, reset, purge, or quarantine command in v1.

Every response should include `schema_version`, `ok`, `command`, `data`, `warnings`, and a structured `error` with a stable code, retryability, and hint. Suggested error codes include `E_USAGE`, `E_POLICY_DENIED`, `E_PATH_NOT_ALLOWED`, `E_CONFLICT_BUSY`, `E_PRECONDITION`, `E_NETWORK`, `E_CHECKSUM`, `E_DEVICE_NONE`, `E_DEVICE_AMBIGUOUS`, `E_DEVICE_UNAUTHORIZED`, `E_BUILD_FAILED`, `E_CANCELLED`, `E_INTERRUPTED`, and `E_INTERNAL`. `ok: true` is valid only after verifying the requested outcome.

Long-running operations should use jobs with explicit states (`queued`, `running`, `waiting_for_user`, `succeeded`, `partial`, `failed`, `cancelled`), ordered events, real progress, and hashed artifacts. Restarted jobs must not be falsely reported as resumed.

## Permissions and safety

Proposed scopes: `inspect`, `setup`, `project.write`, `build`, `device`, and `diagnostics.share`. PATH/Registry changes require a separate `env.write` grant and are denied by default. Destructive operations are out of scope.

Canonicalize paths, enforce configured project roots, defend against traversal and junction/symlink escapes, reject UNC/drive-root project targets, use argument arrays rather than `shell=True`, limit output and runtime, and serialize conflicting jobs. Treat project files and logs as untrusted data, not instructions. Do not auto-elevate or choose the first of multiple connected devices.

FlutterWay runs as the current Windows user; its policy reduces accidental impact but is not a complete security boundary against malicious software running as that user. The harness sandbox remains important.

## MCP and harness support

Use stdio only in v1; do not open a TCP listener. MCP tools must map one-to-one to CLI operations and must not duplicate business logic. Mark inspection tools read-only; require client approval for setup, project writes, builds, and device actions. A future skill can teach the workflow but cannot enforce permissions.

Acceptance requires the same end-to-end scenario on at least two different harnesses, ideally using CLI on one and MCP on another. Test quoting, approvals, timeouts, stdout/stderr handling, and cancellation.

## Implementation phases

| Phase | Deliverable | Exit gate |
|---|---|---|
| P0 — Contract/design | ADRs, schemas, threat model | Review before implementation. |
| P1 — Read-only core | `capabilities`, `doctor`, service separation | Headless operation and schema-valid output on clean Windows. |
| P2 — Setup jobs | Plan/apply, progress, locks, cancellation | Isolated data root, unchanged canary project, truthful outcomes. |
| P3 — Project/build/device | Create, build, run, device listing | Verified APK and physical-device test; explicit multi-device error. |
| P4 — MCP | stdio adapter and tools | MCP result matches CLI behavior. |
| P5 — Distribution | `fway.exe`, docs, optional skill | Two harnesses pass the same scenario. |
| P6 — Optional | Hot Reload, diagnostics, screenshots | Separate decision and review. |

These are planning estimates, not commitments. Acceptance gates take precedence.

## Verification

Cover policy, paths, schemas, error/exit codes, job states, cancellation, duplicate operations, network/disk failures, and output limits in unit and integration tests. Include malicious path, UNC, junction, shell-metacharacter, unauthorized-device, multiple-device, invalid-job, and prompt-injection fixtures. Hash an existing canary project before and after each scenario; any change fails the test. GitHub-hosted CI cannot claim physical USB coverage, so device tests remain manual or self-hosted.

## Open decisions

- Choose the first two acceptance harnesses (proposed: Codex CLI plus OpenCode or Claude Code).
- Keep environment changes denied by default; require explicit `env.write` consent.
- Keep project creation restricted to configured roots.
- Defer local HTTP, Hot Reload, and destructive operations.
- Use stable language-independent error codes, with localized English/Arabic messages where useful.
- Use `fway` as the proposed command name.

## References

- OpenAI, [Harness engineering](https://openai.com/index/harness-engineering/).
- [Codex MCP documentation](https://developers.openai.com/codex/mcp/).
- [Codex skills documentation](https://developers.openai.com/codex/skills/).
- [AGENTS.md standard](https://agents.md/).
