"""EP-056 capability registry module: the "capability" command namespace (Capability Learning).

Implements `CommandModule` (`src/core/command_router.py`), following
`DesktopModule`/`BrowserModule`/`FileModule`/`VisionModule`/
`ReflectionModule`/`PromptOptimizerModule`'s reference-implementation
pattern exactly (Owner Decision D7, `EP056_DESIGN.md`). Bridges an
on-demand Capability Registry (Owner Decision D1, "Candidate A") to
the "capability" namespace, dispatched through the *existing*,
unmodified `CommandRouter.dispatch()` -- no new dispatch mechanism,
and Tool Engine is untouched.

Like `ReflectionModule` (EP-054) and `PromptOptimizerModule` (EP-055),
and unlike `desktop`/`browser`/`file`/`vision`, EP-056 introduces no
new external I/O surface and therefore no new backend Protocol
(`EP056_DESIGN.md` Section 6.2): `CapabilityRegistryModule` composes
three already-existing, unmodified components directly via
constructor injection --

    - `PluginService` (EP-010) -- `PluginService.running_plugins()`
      returns every plugin currently reporting RUNNING status, each
      already carrying `id`/`name`/`description`/`capabilities`
      (free-form capability tags, already validated by
      `PluginManifest`). This is the one real, already-populated
      "capabilities" data model that exists anywhere in the
      repository (`EP056_DESIGN.md` Section 3.2) -- read-only, never
      modified.
    - `CommandRouter` -- `module_names()` returns the bare list of
      currently-registered namespaces (e.g. "desktop", "reflect",
      "prompt"). No richer per-skill description exists without
      extending the `CommandModule` Protocol itself, which
      `EP056_DESIGN.md` Section 4/Candidate D explicitly declines for
      v1 as a cross-cutting change to every existing skill -- so only
      bare namespace names are included, never invented descriptions.
    - `PromptManager` (EP-017) -- `PromptManager.build(capabilities=
      [...])` is called only by the `inject` action (Owner Decision
      D2), passing the composed summary through the Prompt Engine's
      already-existing, currently-unused "Capability Context" seam
      (`PromptBuilder.append_capabilities()`,
      `src/core/ai/prompt_builder.py`) -- whose own docstring reads
      "reserved for the future Capability Registry"
      (`EP056_DESIGN.md` Section 3.3). This module is that Capability
      Registry. No AI-provider call is ever made by this module --
      `inject` returns the assembled `Prompt.rendered` text directly,
      for inspection, never calling `AIProvider.ask()`.

`src/core/plugins/plugin.py`, `plugin_manifest.py`,
`plugin_registry.py`, `plugin_loader.py`, `plugin_discovery.py`,
`src/services/plugin_service.py`, `src/core/command_router.py`, and
`src/core/ai/prompt.py`/`prompt_builder.py`/`prompt_manager.py` are
all completely unmodified by EP-056 (`EP056_DESIGN.md` Section 14, DO
NOT MODIFY) -- every one of these components is used exclusively
through its existing, unmodified public API.

Bootstrap ordering note (`EP056_DESIGN.md` Section 3.8/D5):
`CapabilityRegistryModule` depends on `plugin_service`, which is not
constructed until much later in `src/bootstrap.py` than
`ai_provider_manager`/`prompt_manager` -- so this module is registered
at (not before) `plugin_service`'s own existing construction site, not
alongside the Prompt Engine's own wiring.

Safety model (`EP056_DESIGN.md` Section 7/20, Owner Decisions
D1/D3):

    1. `capability_registry.enabled` (default `false`) -- the master
       gate for the entire namespace, re-checked on every dispatched
       action, not only at registration time (mirrors
       `reflection.enabled`/`prompt_optimizer.enabled`/
       `vision.enabled`/`file.enabled`/`browser.enabled`/
       `desktop.enabled` exactly). `CapabilityRegistryModule` IS
       registered with `CommandRouter` regardless of this flag's
       value.
    2. No AI-provider call, no filesystem write, and no resource/rate
       limit exists anywhere in this module (Owner Decision D3,
       `EP056_DESIGN.md` Section 7/17) -- `capability list`/`capability
       inject` disclose nothing the already-existing, unmodified
       `plugin status`/`plugin info` commands do not already disclose
       today.

No shell/subprocess/arbitrary code execution of any kind exists in
this module, and no new third-party dependency was introduced
(`EP056_DESIGN.md` Section 9).
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from src.core.ai.prompt_builder import PromptTemplateNotFoundError, PromptValidationError
from src.core.ai.prompt_manager import PromptManager
from src.core.command_router import CommandResult
from src.core.config import Config
from src.services.plugin_service import PluginService

HELP_TEXT: str = (
    "Available capability commands (Capability Registry, EP-056)\n\n"
    "capability help\n"
    "capability list\n"
    "capability inject <text>\n\n"
    "'capability list' composes a summary of Jarvis's currently\n"
    "available capabilities -- each running plugin's declared\n"
    "capability tags, plus the bare list of registered built-in\n"
    "commands. 'capability inject' passes that same summary through\n"
    "the Prompt Engine's existing 'Capability Context' stage\n"
    "(PromptManager.build(capabilities=...)) together with <text>,\n"
    "returning the assembled prompt for inspection -- it never calls\n"
    "an AI provider."
)

ActionHandler = Callable[[list[str]], CommandResult]

_DISABLED_MESSAGE: str = (
    "Capability Registry is disabled ('capability_registry.enabled: "
    "false' in config/config.yaml). Set it to true and restart to "
    "enable 'capability' actions."
)


class CapabilityRegistryModule:
    """The "capability" command namespace (EP-056, Capability Learning).

    Responsibilities:
        - `capability list`: compose and return a summary of Jarvis's
          currently available capabilities, from already-existing,
          already-populated data only (`PluginService.
          running_plugins()`, `CommandRouter.module_names()`).
        - `capability inject <text>`: compose the same summary and
          pass it, together with `<text>`, through
          `PromptManager.build(capabilities=[...])`, returning the
          assembled `Prompt.rendered` text.

    Never modifies a plugin, a prompt template, or a router
    registration; never calls an AI provider; never writes to the
    filesystem; never autonomously changes any configuration or other
    component's behavior.
    """

    def __init__(
        self,
        config: Config,
        plugin_service: PluginService,
        module_names: Callable[[], list[str]],
        prompt_manager: PromptManager,
    ) -> None:
        """Initialize the CapabilityRegistryModule.

        Args:
            config: The application Config. Read at dispatch time for
                'capability_registry.enabled' -- read fresh on every
                call, not cached, so a config reload/restart is the
                only way to change it.
            plugin_service: The already-constructed `PluginService`
                (EP-010), used only via `running_plugins()`.
            module_names: A zero-argument callable returning the
                currently-registered `CommandRouter` namespaces (i.e.
                `CommandRouter.module_names`, passed as a bound
                method) -- injected as a callable rather than the
                router itself so this module depends on exactly the
                one read-only capability it needs, nothing more.
            prompt_manager: The already-constructed `PromptManager`
                (EP-017), used only by `capability inject` via
                `build(capabilities=[...])`. Never used to modify any
                existing Prompt Engine behavior -- `PromptManager`
                already supports multiple, independent `Prompt`
                objects concurrently by design.
        """
        self._config = config
        self._plugin_service = plugin_service
        self._module_names = module_names
        self._prompt_manager = prompt_manager
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "list": self._list,
            "inject": self._inject,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "capability".
        """
        return "capability"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "capability" action.

        Args:
            action: The requested action (e.g. "list"). May be empty
                if the user entered only "capability".
            arguments: Additional arguments, meaning depends on the
                action (see `HELP_TEXT`).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            logger.info(f"Unknown command: {command}")
            message = (
                f"Unknown command: {command}\n"
                'Type "capability help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    # ---------- Safety gate (EP056_DESIGN.md Section 7/20) ----------

    def _is_enabled(self) -> bool:
        """Return whether 'capability_registry.enabled' is currently true."""
        return bool(self._config.get("capability_registry.enabled", False))

    def _gate(self) -> CommandResult | None:
        """Return a failure CommandResult if no action may execute, else None.

        Called by every action handler *after* argument-shape
        validation and *before* any read of `PluginService`/
        `CommandRouter`/`PromptManager` -- guarantees zero downstream
        calls while disabled, matching the corrected ordering
        `PromptOptimizerModule` (EP-055 STEP 4, Owner Decision D10)
        already established: shape validation first, then the gate,
        then everything else.
        """
        if not self._is_enabled():
            logger.info("capability: action rejected, 'capability_registry.enabled' is false.")
            return CommandResult(success=False, message=_DISABLED_MESSAGE)
        return None

    # ---------- Action handlers ----------

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available capability commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """Compose and return the current Capability Context summary.

        Args:
            arguments: Must be empty -- `capability list` takes no
                arguments.
        """
        if arguments:
            return _usage_error("capability list")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        summary = self._compose_summary()
        return CommandResult(success=True, message=summary)

    def _inject(self, arguments: list[str]) -> CommandResult:
        """Compose the Capability Context and inject it via the Prompt Engine.

        Args:
            arguments: One-or-more free-text words joined with a
                single space (matching the existing `" ".join(arguments)`
                convention already used elsewhere for free-text
                command arguments, e.g. `prompt optimize`,
                `src/skills/prompt_optimizer/skill.py`).
        """
        if not arguments or not " ".join(arguments).strip():
            return _usage_error("capability inject <text>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        user_prompt = " ".join(arguments).strip()
        summary = self._compose_summary()

        try:
            prompt = self._prompt_manager.build(user_prompt=user_prompt, capabilities=[summary])
        except (PromptValidationError, PromptTemplateNotFoundError) as exc:
            logger.error(f"capability inject failed: {exc}")
            return CommandResult(success=False, message=f"capability inject failed: {exc}")

        return CommandResult(success=True, message=prompt.rendered)

    # ---------- Summary composition ----------

    def _compose_summary(self) -> str:
        """Compose the Capability Context summary from already-existing data only.

        Returns:
            A human/AI-readable summary of every currently-RUNNING
            plugin's declared id/name/description/capabilities, plus
            the bare list of currently-registered `CommandRouter`
            namespaces. Never empty -- reports "(none)" for either
            section when there is nothing to list, rather than
            raising.
        """
        lines: list[str] = ["Capability Registry (EP-056):", ""]

        plugins = self._plugin_service.running_plugins()
        lines.append("Plugins:")
        if plugins:
            for plugin in plugins:
                tags = ", ".join(plugin.capabilities) if plugin.capabilities else "(none declared)"
                lines.append(f"- {plugin.id} ({plugin.name}): {plugin.description}. Capabilities: {tags}.")
        else:
            lines.append("- (none currently running)")

        lines.append("")
        namespaces = sorted(self._module_names())
        lines.append(f"Built-in commands: {', '.join(namespaces) if namespaces else '(none)'}")

        return "\n".join(lines)


def _usage_error(usage: str) -> CommandResult:
    """Return a standard, non-crashing usage-error CommandResult."""
    return CommandResult(success=False, message=f"Invalid arguments. Usage: {usage}")
