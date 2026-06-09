# Excel Check

Excel Check is a configuration-table validation and lookup context for game configuration work. The language below defines project-specific terms used across personal checks, project checks, Feishu bot commands, and configuration-table query workflows.

## Language

**Query Rule Configuration**:
A single project-level Markdown document that defines which configuration table can be queried, how user input maps to rows, and which fields should be returned in a Feishu bot response.
_Avoid_: Prompt file, AI config, query script, cross-project rule

**Query Rule Workspace**:
A project-member-visible workspace where users can view and edit Markdown query rule configurations, while the platform validates and publishes only deterministic, parseable query definitions.
_Avoid_: Admin-only bot settings, free-form prompt editor, runtime command

**Rule Configuration Workspace**:
A project-member-visible workspace for Markdown-authored project rules across multiple purposes, where each rule family has deterministic validation and only published versions can affect runtime behavior.
_Avoid_: Admin-only settings, personal workbench config, unchecked Markdown editor

**Rule Configuration Home**:
The entry view of the rule configuration workspace where project members browse rule families, see publication status, and open a rule family for editing.
_Avoid_: Rule editor, admin bot settings

**Rule Configuration Editor**:
The detailed rule configuration workspace view where project members edit Markdown, validate structure, publish versions, review history, inspect credential status, and run lookup trials.
_Avoid_: Rule list, global settings, AI prompt editor

**Rule Family**:
A category of project rule configuration with its own Markdown schema, validator, parser, and runtime consumer; the initial rule family is `config_lookup`.
_Avoid_: Rule group, query type, UI tab

**Project-Scoped Rule Configuration**:
A rule configuration owned by one project, so different projects may publish different Markdown rules while sharing the same platform runtime behavior.
_Avoid_: Global rule configuration, cross-project rule fallback

**Chinese Rule Configuration Language**:
A user-facing Markdown rule language that uses a fixed set of Chinese labels for configuration authors, while the platform maps those labels into deterministic internal rule fields. The first version supports only Chinese configuration labels and does not accept synonyms.
_Avoid_: English-only schema, dual-language schema, synonym schema, AI-parsed prose, developer-facing config

**Published Query Rule Version**:
A query rule configuration version that passed deterministic validation and is active immediately for Feishu bot lookups, regardless of who edited it and without requiring bot reconnection.
_Avoid_: Draft, latest edit, unvalidated Markdown, restart-gated rule, cross-project published rule

**Project-Scoped Query Rule**:
A query rule configuration that belongs to exactly one project. The same query type may exist in different projects with different files, sheets, roots, and output fields.
_Avoid_: System-wide query rule, shared query type definition

**Missing Published Query Rule**:
A project state where no validated query rule configuration has been published yet, so Feishu bot lookup commands cannot run and should direct users to publish from the rule configuration workspace.
_Avoid_: Empty lookup result, missing query type, SVN failure

**Rule Publication Conflict**:
A save or publish attempt based on an older query rule draft version after another project member has already changed the same rule configuration.
_Avoid_: Silent overwrite, last-write-wins

**Query Rule Draft**:
An editable Markdown query rule configuration version that is visible in the query rule workspace but is not used by Feishu bot lookups until it passes validation and is published.
_Avoid_: Published rule, runtime config

**Configuration Table Lookup**:
A Feishu bot workflow that searches approved configuration table files according to a query rule configuration and replies to the originating group with selected configuration fields.
_Avoid_: Project check, directory query, file download

**Reusable Bot Lookup Runtime**:
The shared Feishu bot lookup implementation that executes project-scoped rule configurations according to the project context of the received bot event.
_Avoid_: Shared project rules, global bot state

**Shared Feishu Bot App**:
A Feishu bot application that can serve multiple projects through the same App ID while each project still maintains its own bot configuration, rule configuration, and credentials.
_Avoid_: One-app-one-project assumption, global project configuration

**Shared Bot Credential Consistency**:
A requirement that projects reusing the same Feishu App ID must configure the same App Secret, so one shared bot connection can authenticate consistently while routing messages by chat binding.
_Avoid_: Per-project secret divergence for one App ID, ambiguous bot authentication

**Per-Project Bot Configuration**:
A Feishu bot configuration edited from a single project's admin area. Different projects may use the same Feishu App ID or different App IDs, but each project's chat bindings, trigger allowlist, download roots, query roots, and credentials remain separately configured.
_Avoid_: Global bot configuration, merged project settings, shared download roots

**Chat-Scoped Project Routing**:
A bot event routing model where the incoming Feishu chat context determines which project-scoped rule configuration should handle the command. One Feishu group chat may be bound to only one project.
_Avoid_: App-ID-only project routing, sender-selected project fallback, cross-project rule lookup, multi-project chat binding

**Unbound Bot Chat**:
A Feishu chat that sends a command to a shared bot app but is not bound to any project; the bot records the event without replying.
_Avoid_: Default project fallback, public setup prompt

**Project Chat Binding**:
A project-level Feishu group binding where one project may bind multiple Feishu group chats, while each group chat belongs to only one project. Attempts to bind a chat already owned by another project are rejected with the existing project name.
_Avoid_: User-selected project in chat, duplicate chat ownership

**Default Bot Chat**:
The single project-level Feishu chat used for default proactive notifications, while command responses are sent back to the chat where the command was received. The default bot chat must also be included in the project's chat bindings.
_Avoid_: Exclusive chat binding, command response override, unbound default chat

**Project Bot Trigger Allowlist**:
A project-level list of Feishu users allowed to trigger bot commands across all group chats bound to that project. An empty allowlist means no sender restriction; users outside a non-empty allowlist receive the generic message `当前用户无机器人指令执行权限`.
_Avoid_: Chat-specific trigger list, global user allowlist, project-check-only permission wording

**Unified Bot Project Configuration**:
A project-level bot configuration that reuses existing Feishu bot download settings and is extended for configuration-table lookup instead of introducing a separate lookup-only bot configuration.
_Avoid_: Parallel bot config, lookup-only project settings

**Query Type**:
A deterministic, project-unique command routing key declared in a query rule configuration, such as `礼包`, that selects one lookup definition before any table search or AI-assisted name match occurs.
_Avoid_: AI intent, natural-language category

**Missing Query Type**:
A lookup command state where the requested query type is not present in the currently published query rule configuration, including query types that existed in older versions but were removed.
_Avoid_: Historical fallback, deleted rule execution

**Lookup Command**:
A Feishu bot command shaped as query type, action, versioned config folder, and lookup input; for example `礼包 查询 /datas 26051802`. A compact form such as `礼包查询` is only a compatibility alias for the same query type plus action.
_Avoid_: Natural-language prompt, arbitrary bot sentence

**Query Definition Group**:
A named section inside a query rule configuration that declares one query type and its table, matching, and response rules, such as `礼包` or `玩法开关`.
_Avoid_: AI route, hardcoded command, one-off script

**Primary Lookup File**:
The configuration table file in a query definition group where ID and name matching are performed.
_Avoid_: Reference file, output-only lookup source

**Reference Lookup File**:
An optional configuration table file used to enrich lookup output after the primary lookup file has produced a matched row.
_Avoid_: Primary match source, query route

**Lookup Join**:
An explicit field mapping from a matched primary lookup row to a reference lookup file, used to enrich output without guessing relationships.
_Avoid_: Automatic join inference, fuzzy association

**Lookup Result Entry**:
One matched row returned from a primary lookup file and sheet, optionally enriched by reference lookup files; a single lookup command may return multiple result entries, and each entry returns the output fields declared in configuration.
_Avoid_: Whole command result, candidate suggestion

**Lookup Result Delivery**:
The Feishu bot message delivery of lookup result entries. Lookup semantics return all matched entries, while delivery may split entries across multiple messages to stay readable and within platform limits.
_Avoid_: Result truncation, business pagination

**Lookup Output Field**:
A configured field returned in a lookup result entry, declared either as a plain field name or as an object with `field` and optional `label` presentation metadata.
_Avoid_: Match field, AI explanation, unconfigured field, enum formatter

**AI-Assisted Name Match**:
A lookup step where AI may rank or normalize user-entered names against deterministic candidates, without changing the query rule configuration or selecting files, sheets, or output fields.
_Avoid_: AI query execution, AI rule parsing

**Lookup Input Resolution**:
A deterministic lookup step where purely numeric input is first treated as an exact ID; non-numeric input, or numeric input whose ID lookup misses, may proceed to an AI-assisted name match.
_Avoid_: Free-form AI search, semantic query execution

**Ambiguous Lookup Match**:
A lookup state where AI-assisted name matching finds multiple plausible candidates or no candidate above the automatic match confidence threshold, so the bot replies with candidate IDs or a miss message instead of a configuration detail result.
_Avoid_: Best guess, fuzzy success

**Lookup Validation Scope**:
The validation depth applied before publishing a query rule configuration. The first version validates Markdown structure and deterministic rule fields without requiring live SVN Excel field checks.
_Avoid_: Runtime lookup execution, AI validation

**Lookup Trial Run**:
A user-triggered, non-publishing check from the rule configuration workspace that reads the configured SVN Excel files for a supplied versioned config folder and lookup input to verify a published or draft lookup rule.
_Avoid_: Publication validation, scheduled check, bot command

**Configured Query Root**:
An administrator-approved local or SVN root directory that bounds which Markdown query rule configurations and configuration table files a Feishu bot command may read.
_Avoid_: Arbitrary path, free-form file path

**Remote SVN Query Root**:
An administrator-approved SVN directory URL that acts as the fixed upper boundary for configuration-table lookup across multiple versioned configuration folders and is referenced by a safe query root alias in rule configuration.
_Avoid_: User-provided SVN URL, Markdown-authored root URL, direct remote Excel parsing

**Query Root Alias**:
A stable machine-readable identifier for a configured query root, written in Markdown rule configuration while the UI may show a separate Chinese display name for confirmation.
_Avoid_: Display name, SVN URL, versioned config folder

**Versioned Config Folder**:
A user-selected relative folder under a remote SVN query root, such as `/datas`, that chooses which version or environment of configuration tables should be searched. It must stay within the selected query root, cannot be an absolute URL, drive path, or parent-directory escape, and is not replaced by a directory alias in the first version.
_Avoid_: SVN root, file name, query type, arbitrary path, directory alias

**Missing Versioned Config Folder**:
A lookup failure state where the user-selected versioned config folder does not exist under the configured query root.
_Avoid_: Missing query type, missing published rule, configuration file not found

**Missing Lookup File**:
A lookup failure state where a configuration file declared by a query definition group does not exist under the selected versioned config folder.
_Avoid_: Missing versioned config folder, missing sheet, missing query type

**Project AI Credential**:
An administrator-managed AI provider credential owned by a project and used by project-level automation such as Feishu bot configuration-table lookups.
_Avoid_: Personal AI key, bot user key, shared admin key

**Project Credential Status**:
A credential visibility state shown to project members without exposing secrets, such as whether SVN or AI credentials are configured and when they were last updated. Ordinary project members may view status but may not trigger credential connection tests.
_Avoid_: Secret value, password display, API key display, member-triggered credential test
