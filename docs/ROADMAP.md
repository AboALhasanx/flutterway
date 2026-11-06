# FlutterWay Engineering Roadmap

> **Status:** This roadmap includes future architecture proposals. Some Go-engine items, the `fway.exe` CLI, and dynamic-manifest design are not implemented in the current Python + pywebview app. See [README](../README.md) for the current implementation.

**Language:** [English](ROADMAP.md) | [العربية](ar/ROADMAP.md)

---

## Phase 1: Core engine in Go — future proposal

- [x] Create a modular Go repository structure.
- [x] Draft and review software requirements and architecture documents.
- [x] Design the dynamic toolchain manifest (`manifests/toolchain-v1.json`).
- [ ] Implement system and registry inspection (`pkg/inspector`, `pkg/sysenv`).
- [ ] Implement ADB and connected-device inspection (`pkg/inspector/adb.go`).
- [ ] Implement resumable, chunked downloads (`pkg/downloader`).
- [ ] Implement toolchain installers (`pkg/installer`).
- [ ] Build local Doctor rules and repair engine (`pkg/doctor`).
- [ ] Build the CLI entry point (`cmd/fway/main.go`).

---

## Phase 2: Unit and integration testing

- [ ] Test path normalization with spaces and non-ASCII characters.
- [ ] Simulate ADB failures and port 5037 conflicts with BlueStacks/Nox.
- [ ] Test resumable downloads and SHA-256 verification.
- [ ] Test `fway doctor --json` on multiple Windows 10 and 11 environments.

---

## Phase 3: Interactive GUI

- [ ] Build the visual step-by-step setup wizard.
- [ ] Provide live download and extraction progress with percentage and speed.
- [ ] Build a mobile build-pipeline diagnostics dashboard.
- [ ] Add one-click guided repair actions.

---

## Phase 4: Packaging and offline distribution

- [ ] Build the offline USB bundle script (`scripts/pack-offline-usb.ps1`).
- [ ] Produce a single-file Windows installer using Inno Setup.
- [ ] Document workflows for students, instructors, and university IT staff.

---

## Phase 5: Agent automation — future work

> Full design and threat model: [Agent Automation Plan](AGENT_AUTOMATION_PLAN.md). Arabic translation: [`ar/AGENT_AUTOMATION_PLAN.md`](ar/AGENT_AUTOMATION_PLAN.md).
>
> Tracking: [GitHub Issue #1](https://github.com/AboALhasanx/flutterway/issues/1).

The goal is to make FlutterWay usable from any Agent Harness (Codex, Claude Code, OpenCode, and others) through a stable CLI/JSON contract and an optional MCP adapter, reusing the same services and safeguards as the GUI.

- [ ] **P0:** Define the contract (JSON Schema, error codes, job states, and permission model).
- [ ] **P1:** Implement headless `fway capabilities` and `fway doctor`; separate setup services from the GUI.
- [ ] **P2:** Implement `setup plan/apply` as observable, cancellable jobs.
- [ ] **P3:** Add project creation, device listing, APK builds, and execution on an explicitly selected device.
- [ ] **P4:** Add a local stdio MCP server whose tools map to CLI operations.
- [ ] **P5:** Package `fway.exe`, provide an optional skill and documentation, and verify with two different harnesses.
- [ ] **P6 (optional):** Consider Hot Reload and diagnostics export; do not add automatic destructive actions.

**Out of scope:** permanent deletion, full reset, arbitrary shell execution, and cloud control.
