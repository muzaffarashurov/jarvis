"""Real engineering tests for EP018.5 - Unified Prompt Budget.

Locks in the fix for the "Prompt exceeds maximum size (~46300
characters)" bug: 'context.max_context_size' and 'prompt.
max_prompt_size' used to be two independent, unreconciled ceilings.
PromptBuilder is now the project's ONE prompt-size authority, and
ContextLoader derives its document budget from it via an injected
`document_budget` callable (Dependency Injection). These tests use
real objects throughout (no mocked internals), matching every other
EP's test suite in this project.
"""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

from src.core.ai.context_manager import ContextManager
from src.core.ai.conversation import Conversation
from src.core.ai.prompt_builder import PromptBuilder, PromptValidationError
from src.core.ai.prompt_manager import PromptManager
from src.core.config import Config
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _write_config(directory: Path, extra_prompt_settings: str = "") -> Config:
    """Write a minimal, self-contained config.yaml and load it.

    Only the keys these tests actually exercise are set; every other
    key BaseTest's classes might touch resolves to its own built-in
    default via `Config.get`'s `default` argument, exactly as it would
    for an operator who never configured it.
    """
    config_path = directory / "config.yaml"
    config_path.write_text(
        "prompt:\n"
        "  max_prompt_size: 1000\n"
        f"{extra_prompt_settings}",
        encoding="utf-8",
    )
    return Config(config_path).load()


@TestRegistry.register
class UnifiedPromptBudgetTest(BaseTest):
    """Real tests covering EP018.5's Unified Prompt Budget (single size authority)."""

    NAME = "EP018"

    def run(self):
        """Execute all Unified Prompt Budget checks and return the aggregated result."""
        self._test_resolve_max_prompt_size_reads_config()
        self._test_resolve_document_budget_subtracts_reserved_space()
        self._test_resolve_document_budget_uses_defaults_when_unset()
        self._test_document_budget_never_goes_negative()
        self._test_invalid_max_prompt_size_raises_validation_error()
        self._test_invalid_reserved_setting_raises_validation_error()
        self._test_prompt_manager_document_budget_matches_prompt_builder()
        self._test_resolve_conversation_budget_matches_reserved_setting()
        self._test_prompt_manager_conversation_budget_matches_prompt_builder()
        self._test_context_manager_requires_document_budget()
        self._test_context_loader_rejects_negative_conversation_budget()
        self._test_conversation_render_keeps_newest_drops_oldest_in_order()
        self._test_conversation_render_within_budget_is_unchanged()
        self._test_end_to_end_oversized_conversation_no_longer_fails()
        self._test_context_loader_rejects_negative_injected_budget()
        self._test_no_independent_context_size_config_remains()
        self._test_end_to_end_oversized_documents_no_longer_fail()
        return self.result

    # ---------- PromptBuilder: the one authority ----------

    def _test_resolve_max_prompt_size_reads_config(self) -> None:
        """PromptBuilder.resolve_max_prompt_size() reads 'prompt.max_prompt_size'."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp))
            self.assert_equal(
                PromptBuilder.resolve_max_prompt_size(config),
                1000,
                "resolve_max_prompt_size should read 'prompt.max_prompt_size' verbatim",
            )

    def _test_resolve_document_budget_subtracts_reserved_space(self) -> None:
        """Document Budget = max_prompt_size - sum(reserved_*), exactly."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                "  reserved_system_prompt: 100\n"
                "  reserved_conversation_history: 200\n"
                "  reserved_user_prompt: 50\n"
                "  reserved_provider_overhead: 25\n",
            )
            expected = 1000 - (100 + 200 + 50 + 25)
            self.assert_equal(
                PromptBuilder.resolve_document_budget(config),
                expected,
                "resolve_document_budget should equal max_prompt_size minus every reserved_* setting",
            )

    def _test_resolve_document_budget_uses_defaults_when_unset(self) -> None:
        """Unset reserved_* settings fall back to their DEFAULT_RESERVED_* constants, not to zero."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp))  # no reserved_* keys at all
            from src.core.ai.prompt_builder import (
                DEFAULT_RESERVED_CONVERSATION_HISTORY,
                DEFAULT_RESERVED_PROVIDER_OVERHEAD,
                DEFAULT_RESERVED_SYSTEM_PROMPT,
                DEFAULT_RESERVED_USER_PROMPT,
            )
            expected_reserved = (
                DEFAULT_RESERVED_SYSTEM_PROMPT
                + DEFAULT_RESERVED_CONVERSATION_HISTORY
                + DEFAULT_RESERVED_USER_PROMPT
                + DEFAULT_RESERVED_PROVIDER_OVERHEAD
            )
            self.assert_equal(
                PromptBuilder.resolve_document_budget(config),
                max(0, 1000 - expected_reserved),
                "Missing reserved_* settings should fall back to DEFAULT_RESERVED_* constants",
            )

    def _test_document_budget_never_goes_negative(self) -> None:
        """Reserved space larger than max_prompt_size clamps the budget to zero, not a negative number."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                "  reserved_system_prompt: 5000\n",
            )
            self.assert_equal(
                PromptBuilder.resolve_document_budget(config),
                0,
                "Document budget should clamp to 0, never go negative",
            )

    def _test_invalid_max_prompt_size_raises_validation_error(self) -> None:
        """A non-numeric 'prompt.max_prompt_size' fails loudly as PromptValidationError, not a raw ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("prompt:\n  max_prompt_size: \"not-a-number\"\n", encoding="utf-8")
            config = Config(config_path).load()
            try:
                PromptBuilder.resolve_max_prompt_size(config)
            except PromptValidationError:
                self.assert_true(True, "Invalid max_prompt_size correctly raised PromptValidationError")
            else:
                self.assert_true(False, "Invalid max_prompt_size should have raised PromptValidationError")

    def _test_invalid_reserved_setting_raises_validation_error(self) -> None:
        """A non-numeric 'prompt.reserved_*' setting also fails loudly as PromptValidationError."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "  reserved_user_prompt: \"lots\"\n")
            try:
                PromptBuilder.resolve_document_budget(config)
            except PromptValidationError:
                self.assert_true(True, "Invalid reserved_* setting correctly raised PromptValidationError")
            else:
                self.assert_true(False, "Invalid reserved_* setting should have raised PromptValidationError")

    # ---------- PromptManager: public forwarding, no logic of its own ----------

    def _test_prompt_manager_document_budget_matches_prompt_builder(self) -> None:
        """PromptManager.document_budget() must equal PromptBuilder.resolve_document_budget() exactly."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "  reserved_system_prompt: 100\n")
            pm = PromptManager(config=config)
            self.assert_equal(
                pm.document_budget(),
                PromptBuilder.resolve_document_budget(config),
                "PromptManager.document_budget() should forward to PromptBuilder without adding its own logic",
            )

    # ---------- ContextManager / ContextLoader: DI, no independent budget ----------

    def _test_context_manager_requires_document_budget(self) -> None:
        """ContextManager must not be constructible without explicit budget callables.

        This is the structural guarantee behind EP-018.5/EP-018.6:
        ContextManager cannot silently fall back to some size default
        of its own, because it has none -- the caller must inject one
        for documents and one for conversation history.
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp))
            try:
                ContextManager(config=config)  # type: ignore[call-arg]
            except TypeError:
                self.assert_true(
                    True, "ContextManager correctly requires explicit budget arguments"
                )
            else:
                self.assert_true(
                    False, "ContextManager should not be constructible without document_budget/conversation_budget"
                )

    def _test_context_loader_rejects_negative_injected_budget(self) -> None:
        """A negative injected document_budget is treated as an operator/wiring mistake, not silently clamped."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp))
            cm = ContextManager(config=config, document_budget=lambda: -1, conversation_budget=lambda: 100)
            try:
                cm._loader._resolve_document_budget()
            except ValueError:
                self.assert_true(True, "Negative injected document_budget correctly raised ValueError")
            else:
                self.assert_true(False, "Negative injected document_budget should have raised ValueError")

    def _test_context_loader_rejects_negative_conversation_budget(self) -> None:
        """A negative injected conversation_budget is likewise treated as a wiring mistake (EP-018.6)."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp))
            cm = ContextManager(config=config, document_budget=lambda: 100, conversation_budget=lambda: -1)
            try:
                cm._loader._resolve_conversation_budget()
            except ValueError:
                self.assert_true(True, "Negative injected conversation_budget correctly raised ValueError")
            else:
                self.assert_true(False, "Negative injected conversation_budget should have raised ValueError")

    def _test_no_independent_context_size_config_remains(self) -> None:
        """ContextLoader must expose no leftover method/constant for an independent size ceiling."""
        import src.core.ai.context_loader as context_loader_module

        self.assert_false(
            hasattr(context_loader_module.ContextLoader, "_resolve_max_context_size"),
            "ContextLoader must not define _resolve_max_context_size any more (EP-018.5)",
        )
        self.assert_false(
            hasattr(context_loader_module, "_DEFAULT_MAX_CONTEXT_SIZE"),
            "ContextLoader must not define a standalone default context-size constant any more (EP-018.5)",
        )

    # ---------- End-to-end regression: the original bug report ----------

    def _test_end_to_end_oversized_documents_no_longer_fail(self) -> None:
        """Reproduces the original bug: documents far larger than the prompt budget must no longer fail.

        Before EP-018.5, ContextLoader loaded up to a separately
        configured 'context.max_context_size' (e.g. 50000) while
        PromptBuilder rejected anything above 'prompt.max_prompt_size'
        (e.g. 32000), so any project with enough documentation failed
        on every request with "Prompt exceeds maximum size" regardless
        of the user's question. This builds a real oversized manifest
        + document set and confirms the full ContextManager ->
        PromptManager pipeline now succeeds.
        """
        original_cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                # A single document far larger than any reasonable
                # prompt budget -- this is what used to reproduce the
                # bug regardless of the user's question.
                (project_dir / "BIG_DOC.md").write_text("x" * 60_000, encoding="utf-8")
                (project_dir / "PROJECT_MANIFEST.md").write_text(
                    "# Project Name\n\nRegression Fixture\n\n"
                    "# Context Documents\n\n"
                    "- path: BIG_DOC.md\n  priority: critical\n",
                    encoding="utf-8",
                )
                config = _write_config(project_dir)  # max_prompt_size: 1000, defaults reserved

                os.chdir(project_dir)

                prompt_manager = PromptManager(config=config)
                context_manager = ContextManager(
                    config=config,
                    document_budget=prompt_manager.document_budget,
                    conversation_budget=prompt_manager.conversation_budget,
                )

                context = context_manager.create(query="test", conversation=Conversation())
                self.assert_true(
                    len(context.rendered) <= prompt_manager.document_budget() + 200,
                    "Context.rendered should be capped near the derived document budget, "
                    f"got {len(context.rendered)} chars against a budget of {prompt_manager.document_budget()}",
                )

                try:
                    prompt = prompt_manager.build(user_prompt="test", context=[context.rendered])
                except PromptValidationError:
                    self.assert_true(
                        False,
                        "PromptManager.build() raised PromptValidationError for an oversized document set -- "
                        "this is the exact original bug, still present:\n" + traceback.format_exc(),
                    )
                else:
                    self.assert_true(
                        len(prompt.rendered) <= 1000,
                        f"Built prompt should respect prompt.max_prompt_size (1000), got {len(prompt.rendered)}",
                    )
        finally:
            os.chdir(original_cwd)

    # ---------- EP-018.6: conversation budget resolution ----------

    def _test_resolve_conversation_budget_matches_reserved_setting(self) -> None:
        """resolve_conversation_budget() returns 'prompt.reserved_conversation_history' verbatim.

        It must NOT subtract it from max_prompt_size (that already
        happens once, inside resolve_document_budget()) -- this is
        exposing the same reserved figure as its own budget, not a
        second derivation.
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "  reserved_conversation_history: 500\n")
            self.assert_equal(
                PromptBuilder.resolve_conversation_budget(config),
                500,
                "resolve_conversation_budget should equal 'prompt.reserved_conversation_history' unchanged",
            )

    def _test_prompt_manager_conversation_budget_matches_prompt_builder(self) -> None:
        """PromptManager.conversation_budget() must equal PromptBuilder.resolve_conversation_budget() exactly."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "  reserved_conversation_history: 777\n")
            pm = PromptManager(config=config)
            self.assert_equal(
                pm.conversation_budget(),
                777,
                "PromptManager.conversation_budget() should forward to PromptBuilder without adding its own logic",
            )

    # ---------- EP-018.6: conversation rendering / truncation semantics ----------

    def _test_conversation_render_keeps_newest_drops_oldest_in_order(self) -> None:
        """Given a budget too small for every message, the newest are kept, oldest dropped, order preserved."""
        from src.core.ai.context_loader import ContextLoader

        conversation = Conversation()
        conversation.append_user("oldest message")
        conversation.append_assistant("second message")
        conversation.append_user("newest message")

        # A budget that fits the header plus only the single newest line.
        header = "Conversation Context\n\n"
        newest_line = "user: newest message"
        budget = len(header + newest_line)

        rendered = ContextLoader._render_conversation(conversation, budget)

        self.assert_true(
            "newest message" in rendered,
            "The newest message must be kept when the conversation is truncated",
        )
        self.assert_true(
            "oldest message" not in rendered,
            "The oldest message must be dropped first when the conversation is truncated",
        )
        self.assert_true(
            "second message" not in rendered,
            "Only what fits the budget should be kept -- the second-oldest message should also be dropped here",
        )
        self.assert_true(
            len(rendered) <= budget,
            f"Rendered conversation ({len(rendered)} chars) must never exceed the budget ({budget})",
        )
        # Chronological order must be preserved among whatever IS kept --
        # verified structurally here since only one message survives;
        # multi-message survival is exercised end-to-end below.

    def _test_conversation_render_within_budget_is_unchanged(self) -> None:
        """A conversation that already fits the budget is rendered in full, unchanged, in chronological order."""
        from src.core.ai.context_loader import ContextLoader

        conversation = Conversation()
        conversation.append_user("first")
        conversation.append_assistant("second")
        conversation.append_user("third")

        rendered = ContextLoader._render_conversation(conversation, budget=100_000)

        first_pos = rendered.find("first")
        second_pos = rendered.find("second")
        third_pos = rendered.find("third")
        self.assert_true(
            -1 < first_pos < second_pos < third_pos,
            "All messages should be present and in chronological order when nothing needs to be dropped",
        )

    # ---------- EP-018.6 end-to-end regression: the follow-up bug report ----------

    def _test_end_to_end_oversized_conversation_no_longer_fails(self) -> None:
        """Reproduces the follow-up bug: unbounded Conversation Context must no longer overflow the prompt.

        Before EP-018.6, Project Context was correctly budgeted
        (EP-018.5) but Conversation Context was rendered in full every
        time, regardless of 'prompt.reserved_conversation_history', so
        a long-running conversation alone could still overflow
        'prompt.max_prompt_size' and raise PromptValidationError. This
        builds a conversation far larger than the reserved budget and
        confirms the full ContextManager -> PromptManager pipeline
        both respects the conversation budget and succeeds.
        """
        original_cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp)
                # No project documents at all -- isolates this test to
                # the conversation-budget bug specifically.
                (project_dir / "PROJECT_MANIFEST.md").write_text(
                    "# Project Name\n\nRegression Fixture\n\n# Context Documents\n\n",
                    encoding="utf-8",
                )
                config = _write_config(
                    project_dir,
                    "  reserved_conversation_history: 500\n"
                    "  reserved_system_prompt: 0\n"
                    "  reserved_user_prompt: 50\n"
                    "  reserved_provider_overhead: 0\n",
                )  # max_prompt_size: 1000

                os.chdir(project_dir)

                conversation = Conversation()
                for i in range(200):
                    conversation.append_user(f"message number {i} " + ("x" * 40))
                    conversation.append_assistant(f"reply number {i} " + ("y" * 40))
                # Far larger than the 500-char reserved budget.
                self.assert_true(
                    len(conversation.messages()) * 40 > 500,
                    "Fixture sanity check: the raw conversation must be far larger than the reserved budget",
                )

                prompt_manager = PromptManager(config=config)
                context_manager = ContextManager(
                    config=config,
                    document_budget=prompt_manager.document_budget,
                    conversation_budget=prompt_manager.conversation_budget,
                )

                context = context_manager.create(query="test", conversation=conversation)
                self.assert_true(
                    len(context.conversation_context) <= prompt_manager.conversation_budget(),
                    "Conversation Context must never exceed the reserved conversation budget, "
                    f"got {len(context.conversation_context)} against a budget of "
                    f"{prompt_manager.conversation_budget()}",
                )
                self.assert_true(
                    "message number 199" in context.conversation_context,
                    "The newest messages should survive truncation",
                )
                self.assert_true(
                    "message number 0 " not in context.conversation_context,
                    "The oldest messages should be the ones dropped",
                )

                try:
                    prompt = prompt_manager.build(user_prompt="test", context=[context.rendered])
                except PromptValidationError:
                    self.assert_true(
                        False,
                        "PromptManager.build() raised PromptValidationError for an oversized conversation -- "
                        "the EP-018.6 bug is still present:\n" + traceback.format_exc(),
                    )
                else:
                    self.assert_true(
                        len(prompt.rendered) <= 1000,
                        f"Built prompt should respect prompt.max_prompt_size (1000), got {len(prompt.rendered)}",
                    )
        finally:
            os.chdir(original_cwd)

