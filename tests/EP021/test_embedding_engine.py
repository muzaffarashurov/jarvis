"""Real engineering tests for EP-021 - Provider-Independent Embedding Engine.

Builds real `EmbeddingManager`/`EmbeddingEngine`/`EmbeddingService`
instances (loading a real `Config` from a temporary config.yaml, as in
tests/EP018/test_unified_prompt_budget.py) and drives them exactly as
a caller would -- no mocked internals, matching every other EP's test
suite in this project. A small local `_BrokenEmbeddingProvider` is used
only to exercise `EmbeddingEngine`'s own vector-validation logic
(EP-021's task brief: "validating vectors" is the Engine's
responsibility, not any single provider's).
"""

from __future__ import annotations

import ast
import inspect
import tempfile
from pathlib import Path

from src.core.config import Config
from src.core.embedding import (
    EmbeddingEngine,
    EmbeddingManager,
    EmbeddingProvider,
    EmbeddingProviderConfigurationError,
    EmbeddingProviderHealth,
    EmbeddingProviderNotFoundError,
    EmbeddingProviderRegistryError,
    EmbeddingProviderStatus,
    EmbeddingProviderUnavailableError,
    EmbeddingValidationError,
    NoProviderSelectedError,
)
from src.core.embedding import engine as engine_module
from src.core.embedding import manager as manager_module
from src.core.embedding import provider as provider_module
from src.core.embedding.provider import EmbeddingConfigurationError, EmbeddingError
from src.core.embedding.providers import CloudEmbeddingProvider, LocalHashEmbeddingProvider
from src.core.embedding.providers import cloud_provider as cloud_provider_module
from src.core.embedding.providers import local_provider as local_provider_module
from src.modules.embedding_module import EmbeddingModule
from src.services.embedding_service import EmbeddingService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _BrokenEmbeddingProvider(EmbeddingProvider):
    """A minimal EmbeddingProvider that returns a deliberately malformed vector.

    Used only to prove that EmbeddingEngine -- not the provider --
    validates vectors before returning them to callers.
    """

    def __init__(self, broken_vector: list) -> None:
        self._broken_vector = broken_vector

    def provider_name(self) -> str:
        return "broken"

    def model_name(self) -> str:
        return "broken-v1"

    def dimension(self) -> int:
        return 4

    def embed(self, text: str) -> list:
        return self._broken_vector

    def embed_many(self, texts: list[str]) -> list:
        return [self._broken_vector for _ in texts]


def _write_config(directory: Path, embedding_settings: str) -> Config:
    """Write a minimal, self-contained config.yaml and load it.

    Only 'embedding.*' keys are set; every other key resolves to its
    own built-in default via `Config.get`'s `default` argument, exactly
    as it would for an operator who never configured it.
    """
    config_path = directory / "config.yaml"
    config_path.write_text(embedding_settings, encoding="utf-8")
    return Config(config_path).load()


_DEFAULT_CONFIG_YAML = (
    "embedding:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    "      model: \"local-hash-v1\"\n"
    "      dimension: 8\n"
    "    cloud:\n"
    "      enabled: false\n"
    "      api_key: \"\"\n"
    "      model: \"text-embedding-cloud-v1\"\n"
    "      dimension: 16\n"
)


@TestRegistry.register
class EmbeddingEngineTest(BaseTest):
    """Real tests covering EP-021's Provider-Independent Embedding Engine."""

    NAME = "EP021"

    def run(self):
        """Execute every Embedding Engine check and return the aggregated result."""
        self._test_local_provider_deterministic()
        self._test_local_provider_dimension_and_disabled()
        self._test_local_provider_embed_many_matches_embed()
        self._test_cloud_provider_status_transitions()
        self._test_cloud_provider_raises_on_embed()
        self._test_manager_builds_providers_from_config()
        self._test_manager_default_provider_selection()
        self._test_manager_set_current_and_get_current()
        self._test_manager_unknown_provider_raises()
        self._test_manager_duplicate_registration_raises()
        self._test_manager_disable()
        self._test_manager_disabled_subsystem_has_no_current()
        self._test_engine_embed_text()
        self._test_engine_embed_texts_batches()
        self._test_engine_no_provider_selected()
        self._test_engine_validates_vector_length()
        self._test_engine_validates_vector_type()
        self._test_engine_validates_non_finite_component()
        self._test_engine_dimension()
        self._test_service_status_and_providers()
        self._test_service_use_provider()
        self._test_service_embed_and_dimension()
        self._test_no_retrieval_or_ai_dependencies()
        self._test_exception_hierarchy_common_root()
        self._test_config_validation_rejects_stringified_dimension()
        self._test_config_validation_rejects_non_bool_enabled()
        self._test_config_validation_rejects_empty_model()
        self._test_config_validation_rejects_non_string_api_key()
        self._test_default_provider_unknown_name_raises_with_available_list()
        self._test_default_provider_none_is_valid()
        self._test_default_provider_missing_key_uses_local()
        self._test_get_provider_unknown_name_lists_available()
        self._test_cli_help()
        self._test_cli_status()
        self._test_cli_providers()
        self._test_cli_use_success_and_failure()
        self._test_cli_embed_success_and_missing_argument()
        self._test_cli_dimension()
        self._test_cli_unknown_action()
        return self.result

    # ---------- LocalHashEmbeddingProvider ----------

    def _test_local_provider_deterministic(self) -> None:
        """Identical input always produces the identical output vector."""
        provider = LocalHashEmbeddingProvider(enabled=True, model="local-hash-v1", dimension=8)
        first = provider.embed("hello world")
        second = provider.embed("hello world")
        self.assert_equal(first, second, "Embedding the same text twice should be deterministic")

        different = provider.embed("goodbye world")
        self.assert_true(first != different, "Different texts should produce different vectors")

    def _test_local_provider_dimension_and_disabled(self) -> None:
        """The local provider reports its configured dimension and rejects use when disabled."""
        provider = LocalHashEmbeddingProvider(enabled=True, model="local-hash-v1", dimension=8)
        self.assert_equal(provider.dimension(), 8, "Dimension should match configuration")
        self.assert_equal(provider.provider_name(), "local", "Provider name should be 'local'")
        self.assert_equal(len(provider.embed("x")), 8, "Embed should return a vector of length 8")
        self.assert_equal(
            provider.status(), EmbeddingProviderStatus.AVAILABLE, "Enabled local provider should be AVAILABLE"
        )

        disabled = LocalHashEmbeddingProvider(enabled=False, model="local-hash-v1", dimension=8)
        self.assert_equal(
            disabled.status(), EmbeddingProviderStatus.DISABLED, "Disabled local provider should be DISABLED"
        )
        try:
            disabled.embed("x")
            self.assert_true(False, "Disabled local provider should raise on embed()")
        except EmbeddingProviderConfigurationError:
            self.result.add_pass()

    def _test_local_provider_embed_many_matches_embed(self) -> None:
        """embed_many() returns exactly the same vectors as calling embed() per text."""
        provider = LocalHashEmbeddingProvider(enabled=True, model="local-hash-v1", dimension=8)
        texts = ["alpha", "beta", "gamma"]
        many = provider.embed_many(texts)
        individually = [provider.embed(text) for text in texts]
        self.assert_equal(many, individually, "embed_many should match per-text embed calls")

    # ---------- CloudEmbeddingProvider ----------

    def _test_cloud_provider_status_transitions(self) -> None:
        """Status reflects enabled/api_key configuration, never a network check."""
        disabled = CloudEmbeddingProvider(enabled=False, api_key="", model="m", dimension=16)
        self.assert_equal(disabled.status(), EmbeddingProviderStatus.DISABLED)

        not_configured = CloudEmbeddingProvider(enabled=True, api_key="", model="m", dimension=16)
        self.assert_equal(not_configured.status(), EmbeddingProviderStatus.NOT_CONFIGURED)

        available = CloudEmbeddingProvider(enabled=True, api_key="secret", model="m", dimension=16)
        self.assert_equal(available.status(), EmbeddingProviderStatus.AVAILABLE)
        self.assert_true(available.is_available(), "A configured, enabled provider should be available")

        health: EmbeddingProviderHealth = not_configured.health()
        self.assert_false(health.available, "An unconfigured provider's health should report unavailable")

    def _test_cloud_provider_raises_on_embed(self) -> None:
        """embed()/embed_many() raise the right error for every configuration state."""
        disabled = CloudEmbeddingProvider(enabled=False, api_key="", model="m", dimension=16)
        try:
            disabled.embed("x")
            self.assert_true(False, "Disabled cloud provider should raise on embed()")
        except EmbeddingProviderConfigurationError:
            self.result.add_pass()

        not_configured = CloudEmbeddingProvider(enabled=True, api_key="", model="m", dimension=16)
        try:
            not_configured.embed_many(["x"])
            self.assert_true(False, "Unconfigured cloud provider should raise on embed_many()")
        except EmbeddingProviderConfigurationError:
            self.result.add_pass()

        available = CloudEmbeddingProvider(enabled=True, api_key="secret", model="m", dimension=16)
        try:
            available.embed("x")
            self.assert_true(False, "A configured cloud provider should still raise -- no network access in this EP")
        except EmbeddingProviderUnavailableError:
            self.result.add_pass()

    # ---------- EmbeddingManager ----------

    def _test_manager_builds_providers_from_config(self) -> None:
        """The manager builds 'local' and 'cloud' providers from real Config values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), _DEFAULT_CONFIG_YAML)
            manager = EmbeddingManager(config)

            providers = manager.list_providers()
            names = sorted(provider.provider_name() for provider in providers)
            self.assert_equal(names, ["cloud", "local"], "Manager should build both built-in providers")

            local = manager.get_provider("local")
            self.assert_equal(local.dimension(), 8, "Local provider dimension should come from config")
            cloud = manager.get_provider("cloud")
            self.assert_equal(cloud.dimension(), 16, "Cloud provider dimension should come from config")
            self.assert_equal(
                cloud.status(), EmbeddingProviderStatus.DISABLED,
                "Cloud provider disabled in config (and with no api_key) should be DISABLED",
            )

    def _test_manager_default_provider_selection(self) -> None:
        """'embedding.default_provider' selects the current provider at construction time."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), _DEFAULT_CONFIG_YAML)
            manager = EmbeddingManager(config)
            self.assert_equal(
                manager.current_provider_name(), "local", "Default provider should be selected from config"
            )
            current = manager.get_current()
            self.assert_not_none(current, "get_current() should return the default provider")
            self.assert_equal(current.provider_name(), "local")

    def _test_manager_set_current_and_get_current(self) -> None:
        """set_current() switches the active provider immediately, in memory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), _DEFAULT_CONFIG_YAML)
            manager = EmbeddingManager(config)
            manager.set_current("cloud")
            self.assert_equal(manager.current_provider_name(), "cloud")
            current = manager.get_current()
            self.assert_not_none(current)
            self.assert_equal(current.provider_name(), "cloud")

    def _test_manager_unknown_provider_raises(self) -> None:
        """Selecting or fetching an unregistered provider name raises."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), _DEFAULT_CONFIG_YAML)
            manager = EmbeddingManager(config)
            try:
                manager.set_current("unknown_provider")
                self.assert_true(False, "Selecting an unknown provider should raise")
            except EmbeddingProviderNotFoundError:
                self.result.add_pass()

            try:
                manager.get_provider("unknown_provider")
                self.assert_true(False, "Fetching an unknown provider should raise")
            except EmbeddingProviderNotFoundError:
                self.result.add_pass()

    def _test_manager_duplicate_registration_raises(self) -> None:
        """Registering two providers with the same name raises."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), _DEFAULT_CONFIG_YAML)
            manager = EmbeddingManager(config)
            duplicate = LocalHashEmbeddingProvider(enabled=True, model="dup", dimension=4)
            try:
                manager.register_provider(duplicate)
                self.assert_true(False, "Registering a duplicate provider name should raise")
            except EmbeddingProviderRegistryError:
                self.result.add_pass()

    def _test_manager_disable(self) -> None:
        """disable() turns off the subsystem and clears the current selection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), _DEFAULT_CONFIG_YAML)
            manager = EmbeddingManager(config)
            manager.disable()
            self.assert_false(manager.is_enabled(), "Manager should report disabled")
            self.assert_equal(manager.get_current(), None, "get_current() should return None once disabled")

    def _test_manager_disabled_subsystem_has_no_current(self) -> None:
        """A subsystem disabled via configuration never reports a current provider."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(
                Path(tmp_dir),
                _DEFAULT_CONFIG_YAML.replace("enabled: true\n  default_provider", "enabled: false\n  default_provider"),
            )
            manager = EmbeddingManager(config)
            self.assert_false(manager.is_enabled(), "Manager should read 'embedding.enabled: false'")
            self.assert_equal(manager.get_current(), None, "A disabled subsystem should have no current provider")

    # ---------- EmbeddingEngine ----------

    def _build_manager_and_engine(self, batch_size: int = 16) -> tuple[EmbeddingManager, EmbeddingEngine, Path, tempfile.TemporaryDirectory]:
        """Build a real EmbeddingManager + EmbeddingEngine pair for engine-level tests."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _DEFAULT_CONFIG_YAML)
        manager = EmbeddingManager(config)
        engine = EmbeddingEngine(manager, batch_size=batch_size)
        return manager, engine, Path(tmp_dir.name), tmp_dir

    def _test_engine_embed_text(self) -> None:
        """embed_text() returns a validated vector from the currently selected provider."""
        _manager, engine, _path, tmp_dir = self._build_manager_and_engine()
        try:
            vector = engine.embed_text("hello")
            self.assert_equal(len(vector), 8, "Vector length should match the local provider's dimension")
        finally:
            tmp_dir.cleanup()

    def _test_engine_embed_texts_batches(self) -> None:
        """embed_texts() batches requests and preserves order, even with a tiny batch size."""
        _manager, engine, _path, tmp_dir = self._build_manager_and_engine(batch_size=2)
        try:
            texts = ["a", "b", "c", "d", "e"]
            vectors = engine.embed_texts(texts)
            self.assert_equal(len(vectors), 5, "One vector per input text should be returned")
            for text, vector in zip(texts, vectors):
                self.assert_equal(vector, engine.embed_text(text), "Batched result should match single embed_text")
            self.assert_equal(engine.embed_texts([]), [], "Empty input should return an empty list")
        finally:
            tmp_dir.cleanup()

    def _test_engine_no_provider_selected(self) -> None:
        """embed_text()/embed_texts()/dimension() raise when no provider is selected."""
        _manager, engine, _path, tmp_dir = self._build_manager_and_engine()
        try:
            _manager.disable()
            try:
                engine.embed_text("x")
                self.assert_true(False, "embed_text should raise when no provider is selected")
            except NoProviderSelectedError:
                self.result.add_pass()

            try:
                engine.embed_texts(["x"])
                self.assert_true(False, "embed_texts should raise when no provider is selected")
            except NoProviderSelectedError:
                self.result.add_pass()

            try:
                engine.dimension()
                self.assert_true(False, "dimension should raise when no provider is selected")
            except NoProviderSelectedError:
                self.result.add_pass()
        finally:
            tmp_dir.cleanup()

    def _test_engine_validates_vector_length(self) -> None:
        """The engine rejects a provider response whose vector length is wrong."""
        manager, engine, _path, tmp_dir = self._build_manager_and_engine()
        try:
            broken = _BrokenEmbeddingProvider(broken_vector=[0.1, 0.2, 0.3])  # dimension() says 4
            manager.register_provider(broken)
            manager.set_current("broken")
            try:
                engine.embed_text("x")
                self.assert_true(False, "Engine should reject a vector with the wrong length")
            except EmbeddingValidationError:
                self.result.add_pass()
        finally:
            tmp_dir.cleanup()

    def _test_engine_validates_vector_type(self) -> None:
        """The engine rejects a provider response containing a non-numeric component."""
        manager, engine, _path, tmp_dir = self._build_manager_and_engine()
        try:
            broken = _BrokenEmbeddingProvider(broken_vector=[0.1, "not-a-number", 0.3, 0.4])
            manager.register_provider(broken)
            manager.set_current("broken")
            try:
                engine.embed_text("x")
                self.assert_true(False, "Engine should reject a vector with a non-numeric component")
            except EmbeddingValidationError:
                self.result.add_pass()
        finally:
            tmp_dir.cleanup()

    def _test_engine_validates_non_finite_component(self) -> None:
        """The engine rejects a provider response containing NaN/Infinity."""
        manager, engine, _path, tmp_dir = self._build_manager_and_engine()
        try:
            broken = _BrokenEmbeddingProvider(broken_vector=[0.1, float("nan"), 0.3, 0.4])
            manager.register_provider(broken)
            manager.set_current("broken")
            try:
                engine.embed_text("x")
                self.assert_true(False, "Engine should reject a vector containing NaN")
            except EmbeddingValidationError:
                self.result.add_pass()
        finally:
            tmp_dir.cleanup()

    def _test_engine_dimension(self) -> None:
        """dimension() forwards the currently selected provider's declared dimension."""
        _manager, engine, _path, tmp_dir = self._build_manager_and_engine()
        try:
            self.assert_equal(engine.dimension(), 8, "Engine dimension should match the local provider")
        finally:
            tmp_dir.cleanup()

    # ---------- EmbeddingService ----------

    def _build_service(self) -> tuple[EmbeddingService, tempfile.TemporaryDirectory]:
        """Build a real EmbeddingService (Manager + Engine) for service-level tests."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _DEFAULT_CONFIG_YAML)
        manager = EmbeddingManager(config)
        engine = EmbeddingEngine(manager)
        return EmbeddingService(manager=manager, engine=engine), tmp_dir

    def _test_service_status_and_providers(self) -> None:
        """status() and list_providers() reflect the underlying Manager/Engine state."""
        service, tmp_dir = self._build_service()
        try:
            status = service.status()
            self.assert_true(status.enabled, "Service status should report enabled")
            self.assert_equal(status.current_provider, "local")
            self.assert_equal(status.dimension, 8)
            self.assert_equal(status.registered_provider_count, 2)

            providers = service.list_providers()
            names = sorted(info.name for info in providers)
            self.assert_equal(names, ["cloud", "local"])
            local_info = next(info for info in providers if info.name == "local")
            self.assert_true(local_info.is_current, "Local provider should be marked as current")
            self.assert_true(local_info.available, "Local provider should be available")
        finally:
            tmp_dir.cleanup()

    def _test_service_use_provider(self) -> None:
        """use_provider() selects a real provider and reports failure for an unknown one."""
        service, tmp_dir = self._build_service()
        try:
            result = service.use_provider("cloud")
            self.assert_true(result.success, "Selecting a registered provider should succeed")
            self.assert_equal(service.status().current_provider, "cloud")

            failure = service.use_provider("does_not_exist")
            self.assert_false(failure.success, "Selecting an unknown provider should fail")
        finally:
            tmp_dir.cleanup()

    def _test_service_embed_and_dimension(self) -> None:
        """embed() and dimension() succeed with the local provider and report errors for the cloud provider."""
        service, tmp_dir = self._build_service()
        try:
            result = service.embed("hello world")
            self.assert_true(result.success, "Embedding with the local provider should succeed")
            self.assert_equal(result.dimension, 8)
            self.assert_equal(result.provider, "local")

            success, dimension, error = service.dimension()
            self.assert_true(success)
            self.assert_equal(dimension, 8)
            self.assert_equal(error, "")

            service.use_provider("cloud")
            broken_result = service.embed("hello world")
            self.assert_false(broken_result.success, "Embedding with an unconfigured cloud provider should fail")
            self.assert_true(bool(broken_result.error), "A failed embed() should carry an error message")
        finally:
            tmp_dir.cleanup()

    # ---------- Architectural acceptance criteria ----------

    def _test_no_retrieval_or_ai_dependencies(self) -> None:
        """The embedding package never imports Retrieval, RAG, or any chat-completion module."""
        forbidden_module_fragments = (
            "retrieval",
            "ranking",
            "rag",
            "src.core.ai",
            "claude_provider",
            "gemini_provider",
            "conversation_manager",
            "prompt_builder",
            "context_loader",
            "context_manager",
        )
        modules = [
            provider_module,
            manager_module,
            engine_module,
            local_provider_module,
            cloud_provider_module,
        ]
        for module in modules:
            tree = ast.parse(inspect.getsource(module))
            imported_names: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_names.append(node.module)
            for imported_name in imported_names:
                lowered = imported_name.lower()
                for forbidden_fragment in forbidden_module_fragments:
                    self.assert_true(
                        forbidden_fragment not in lowered,
                        f"{module.__name__} should never import '{imported_name}'",
                    )

    # ---------- Common exception hierarchy (review fix #4) ----------

    def _test_exception_hierarchy_common_root(self) -> None:
        """Every embedding exception type is catchable as `EmbeddingError`.

        Downstream packages (e.g. a future RAG Engine or Memory
        Manager) must be able to catch one exception type instead of
        many unrelated ones.
        """
        exception_types = (
            EmbeddingProviderConfigurationError,
            EmbeddingProviderUnavailableError,
            NoProviderSelectedError,
            EmbeddingValidationError,
            EmbeddingProviderRegistryError,
            EmbeddingProviderNotFoundError,
            EmbeddingConfigurationError,
        )
        for exception_type in exception_types:
            self.assert_true(
                issubclass(exception_type, EmbeddingError),
                f"{exception_type.__name__} must inherit from EmbeddingError",
            )

        try:
            raise EmbeddingConfigurationError("boom")
        except EmbeddingError:
            self.result.add_pass()
        else:
            self.assert_true(False, "EmbeddingConfigurationError should be catchable as EmbeddingError")

    # ---------- Configuration validation (review fix #1) ----------

    def _test_config_validation_rejects_stringified_dimension(self) -> None:
        """A quoted dimension (e.g. "512") must raise, not silently become the default.

        This reproduces the exact defect identified in the
        independent architecture review: 'dimension: "512"' used to
        silently resolve to 256 with no warning at all.
        """
        yaml_text = _DEFAULT_CONFIG_YAML.replace(
            '      dimension: 8\n', '      dimension: "512"\n'
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), yaml_text)
            try:
                EmbeddingManager(config)
                self.assert_true(False, "A stringified dimension must raise, not silently fall back")
            except EmbeddingConfigurationError as exc:
                self.assert_true(
                    "embedding.providers.local.dimension" in str(exc),
                    "The error must name the offending configuration key",
                )

    def _test_config_validation_rejects_non_bool_enabled(self) -> None:
        """A non-boolean 'enabled' value must raise a clear configuration error."""
        yaml_text = _DEFAULT_CONFIG_YAML.replace(
            "  enabled: true\n  default_provider", '  enabled: "yes"\n  default_provider'
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), yaml_text)
            try:
                EmbeddingManager(config)
                self.assert_true(False, "A non-boolean 'embedding.enabled' must raise")
            except EmbeddingConfigurationError as exc:
                self.assert_true("embedding.enabled" in str(exc))

    def _test_config_validation_rejects_empty_model(self) -> None:
        """An empty/blank model name must raise instead of being silently replaced."""
        yaml_text = _DEFAULT_CONFIG_YAML.replace(
            '      model: "local-hash-v1"\n', '      model: "   "\n'
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), yaml_text)
            try:
                EmbeddingManager(config)
                self.assert_true(False, "A blank model name must raise")
            except EmbeddingConfigurationError as exc:
                self.assert_true("embedding.providers.local.model" in str(exc))

    def _test_config_validation_rejects_non_string_api_key(self) -> None:
        """A non-string api_key (e.g. a number) must raise instead of being coerced."""
        yaml_text = _DEFAULT_CONFIG_YAML.replace('api_key: ""\n', "api_key: 12345\n")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), yaml_text)
            try:
                EmbeddingManager(config)
                self.assert_true(False, "A non-string api_key must raise")
            except EmbeddingConfigurationError as exc:
                self.assert_true("embedding.providers.cloud.api_key" in str(exc))

    # ---------- default_provider handling (review fix #2) ----------

    def _test_default_provider_unknown_name_raises_with_available_list(self) -> None:
        """An unknown 'default_provider' must name itself and list the available providers.

        This reproduces the second defect identified in the
        independent architecture review: a typo like "locall" used to
        silently result in no provider being selected at all, with no
        indication anything was wrong.
        """
        yaml_text = _DEFAULT_CONFIG_YAML.replace(
            'default_provider: "local"', 'default_provider: "locall"'
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), yaml_text)
            try:
                EmbeddingManager(config)
                self.assert_true(False, "An unknown default_provider name must raise")
            except EmbeddingConfigurationError as exc:
                message = str(exc)
                self.assert_true("locall" in message, "The error must name the exact invalid provider")
                self.assert_true("local" in message and "cloud" in message, "The error must list available providers")

    def _test_default_provider_none_is_valid(self) -> None:
        """'default_provider: "none"' is a valid, explicit "no provider selected" state."""
        yaml_text = _DEFAULT_CONFIG_YAML.replace(
            'default_provider: "local"', 'default_provider: "none"'
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), yaml_text)
            manager = EmbeddingManager(config)
            self.assert_equal(manager.current_provider_name(), None)
            self.assert_true(manager.is_enabled(), "The subsystem itself should remain enabled")

    def _test_default_provider_missing_key_uses_local(self) -> None:
        """A missing 'default_provider' key falls back to the documented default: "local"."""
        yaml_text = (
            "embedding:\n"
            "  providers:\n"
            "    local:\n"
            "      enabled: true\n"
            "      model: \"local-hash-v1\"\n"
            "      dimension: 8\n"
            "    cloud:\n"
            "      enabled: false\n"
            "      api_key: \"\"\n"
            "      model: \"text-embedding-cloud-v1\"\n"
            "      dimension: 16\n"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), yaml_text)
            manager = EmbeddingManager(config)
            self.assert_equal(manager.current_provider_name(), "local")

    def _test_get_provider_unknown_name_lists_available(self) -> None:
        """get_provider()/set_current() for an unknown name lists the available providers too."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), _DEFAULT_CONFIG_YAML)
            manager = EmbeddingManager(config)
            try:
                manager.set_current("does_not_exist")
                self.assert_true(False, "Selecting an unknown provider should raise")
            except EmbeddingProviderNotFoundError as exc:
                message = str(exc)
                self.assert_true("does_not_exist" in message)
                self.assert_true("local" in message and "cloud" in message)

    # ---------- CLI layer: EmbeddingModule (review fix #5) ----------

    def _build_module(self) -> tuple[EmbeddingModule, tempfile.TemporaryDirectory]:
        """Build a real EmbeddingModule (backed by a real Service/Engine/Manager) for CLI tests."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _DEFAULT_CONFIG_YAML)
        manager = EmbeddingManager(config)
        engine = EmbeddingEngine(manager)
        service = EmbeddingService(manager=manager, engine=engine)
        return EmbeddingModule(service), tmp_dir

    def _test_cli_help(self) -> None:
        """`embedding help` lists every documented command."""
        module, tmp_dir = self._build_module()
        try:
            result = module.execute("help", [])
            self.assert_true(result.success)
            for command in ("status", "providers", "use <provider>", "embed", "dimension"):
                self.assert_true(command in result.message, f"help text should mention '{command}'")
        finally:
            tmp_dir.cleanup()

    def _test_cli_status(self) -> None:
        """`embedding status` reports the enabled flag and current provider."""
        module, tmp_dir = self._build_module()
        try:
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("local" in result.message)
            self.assert_true("Enabled" in result.message)
        finally:
            tmp_dir.cleanup()

    def _test_cli_providers(self) -> None:
        """`embedding providers` lists every registered provider by name."""
        module, tmp_dir = self._build_module()
        try:
            result = module.execute("providers", [])
            self.assert_true(result.success)
            self.assert_true("local" in result.message)
            self.assert_true("cloud" in result.message)
        finally:
            tmp_dir.cleanup()

    def _test_cli_use_success_and_failure(self) -> None:
        """`embedding use <provider>` succeeds for a real provider and fails for a bad one/bad arg count."""
        module, tmp_dir = self._build_module()
        try:
            success_result = module.execute("use", ["cloud"])
            self.assert_true(success_result.success)

            failure_result = module.execute("use", ["does_not_exist"])
            self.assert_false(failure_result.success)
            self.assert_true("does_not_exist" in failure_result.message)

            usage_result = module.execute("use", [])
            self.assert_false(usage_result.success, "No arguments should fail with a usage message")

            too_many_result = module.execute("use", ["local", "cloud"])
            self.assert_false(too_many_result.success, "Too many arguments should fail with a usage message")
        finally:
            tmp_dir.cleanup()

    def _test_cli_embed_success_and_missing_argument(self) -> None:
        """`embedding embed "<text>"` succeeds with text and fails cleanly with none."""
        module, tmp_dir = self._build_module()
        try:
            success_result = module.execute("embed", ["hello", "world"])
            self.assert_true(success_result.success)
            self.assert_true("Dimension" in success_result.message)

            missing_arg_result = module.execute("embed", [])
            self.assert_false(missing_arg_result.success, "embed with no text should fail with a usage message")
        finally:
            tmp_dir.cleanup()

    def _test_cli_dimension(self) -> None:
        """`embedding dimension` reports the active provider's dimension."""
        module, tmp_dir = self._build_module()
        try:
            result = module.execute("dimension", [])
            self.assert_true(result.success)
            self.assert_true("8" in result.message)
        finally:
            tmp_dir.cleanup()

    def _test_cli_unknown_action(self) -> None:
        """An unrecognized 'embedding' action fails with a helpful message, not a crash."""
        module, tmp_dir = self._build_module()
        try:
            result = module.execute("not_a_real_action", [])
            self.assert_false(result.success)
            self.assert_true("help" in result.message.lower())
        finally:
            tmp_dir.cleanup()
