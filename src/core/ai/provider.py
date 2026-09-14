"""AI provider domain model for EP-014 AI Provider Manager.

Defines the abstraction every AI provider (Claude, OpenAI, Ollama, LM
Studio, Gemini, DeepSeek, OpenRouter, ...) must implement so the rest
of Jarvis never needs to know which provider is currently active. This
module owns no network access itself and no provider-specific
implementation: it is the structural contract only, matching the
pattern already used for the Plugin SDK (see src/core/plugins/plugin.py)
and the Process Catalog (see src/core/processes/process.py).

Per EP-014's "IMPORTANT" section, identity/status/configuration/health
never perform network requests. EP-015 (Claude Provider) additively
extends this contract with `ask()`, `ping()` and `list_models()` so a
provider that DOES implement real chat communication (e.g.
ClaudeProvider) can be used interchangeably through ProviderManager.
Their base implementations below are non-network no-ops so EP-014's
placeholder providers (ConfigDrivenProvider: openai, ollama, lmstudio)
remain valid AIProvider implementations without any changes.

EP-082 (Text Generation Provider Integration) additively extends
`ask()` with two optional keyword parameters, `temperature` and
`system_prompt`, so standalone content-generation callers (see
`src/services/text_generation_service.py`) can override a provider's
per-request creativity/style without changing its configured default.
Both default to `None`, meaning "no override -- use this provider's
existing configured/default behavior unchanged"; every existing
caller that omits them (`AIService`, `ReflectionModule`,
`PromptOptimizerModule`, and every existing test) is therefore
source- and behavior-compatible with zero changes
(`EP082_DESIGN.md` Section 12). `validate_temperature()` below is the
single, shared validation rule every concrete provider applies to a
non-`None` `temperature` override, so no provider is free to
interpret an invalid value differently (`EP082_DESIGN.md` Section
12.1).

EP-083 (Image Generation Provider Integration) additively extends
this contract with `supports_image_generation()`/`generate_image()`,
for standalone image-generation callers (see
`src/services/image_generation_service.py`). EP-084 (Audio & Speech
Generation Integration) additively extends it again with
`supports_speech_generation()`/`generate_speech()`, for standalone
speech-generation callers (see
`src/services/audio_generation_service.py`). Both pairs default to
"unsupported"/"always raises" respectively, so every existing
provider (including EP-014's placeholder providers) remains a valid
`AIProvider` implementation without any changes other than the one
concrete implementation each EP adds (GeminiProvider, in both cases).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ProviderStatus(str, Enum):
    """Lifecycle status a registered AI provider can report.

    Attributes:
        DISABLED: The provider is turned off in configuration
            ('providers.<name>.enabled' is False).
        NOT_CONFIGURED: The provider is enabled but is missing the
            configuration it needs to be usable (e.g. an API key or
            endpoint).
        AVAILABLE: The provider is enabled and fully configured.
    """

    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True)
class ProviderHealth:
    """Result of a provider's own `health()` check.

    This is a configuration-derived readiness check only -- per
    EP-014, no provider performs a network request to verify
    connectivity.

    Attributes:
        available: Whether the provider reports itself ready for use.
        message: Human-readable explanation of the health result.
    """

    available: bool
    message: str


@dataclass(frozen=True)
class ProviderResponse:
    """Result of a successful `AIProvider.ask()` call (EP-015).

    Attributes:
        text: The model's reply text.
        model: The model identifier that produced the reply.
        latency_ms: Wall-clock time the request took, in milliseconds.
    """

    text: str
    model: str
    latency_ms: float


@dataclass(frozen=True)
class ImageGenerationRequest:
    """A provider-independent request to generate one or more images (EP-083).

    Only fields with a plausible, common meaning across image-
    generation APIs in general are included here -- provider-specific
    options belong in that provider's own `providers.<name>.*`
    configuration, not in this common contract
    (`EP083_DESIGN.md` Section 12).

    This dataclass performs no validation itself beyond the
    immutability a frozen dataclass gives for free. Each concrete
    `AIProvider.generate_image()` implementation validates the fields
    it can actually honor and raises `ProviderConfigurationError` for
    anything it cannot -- the same layering `validate_temperature()`
    already established for `ask()` (EP-082).

    Attributes:
        prompt: The image description. Required, non-empty.
        negative_prompt: What to avoid in the generated image. None
            means no negative prompt is supplied.
        size: Requested output dimensions as "WIDTHxHEIGHT" (e.g.
            "1024x1024"), or None to use the provider's own default.
        number_of_images: How many images to generate. Must be a
            positive integer.
        seed: Optional deterministic seed. None means no seed
            requested (provider default randomness).
    """

    prompt: str
    negative_prompt: str | None = None
    size: str | None = None
    number_of_images: int = 1
    seed: int | None = None


@dataclass(frozen=True)
class GeneratedImage:
    """One generated image (EP-083).

    In-memory only -- EP-083 introduces no file persistence
    (`EP083_DESIGN.md` Section 4).

    Attributes:
        data_base64: The image's raw bytes, base64-encoded.
        mime_type: The image's MIME type (e.g. "image/png").
    """

    data_base64: str
    mime_type: str


@dataclass(frozen=True)
class ImageGenerationResult:
    """Result of a successful `AIProvider.generate_image()` call (EP-083).

    Mirrors `ProviderResponse`'s shape (`model`, `latency_ms`),
    replacing its single `text: str` with `images` -- the smallest
    change that fits the same existing pattern.

    Attributes:
        images: The generated image(s). Always non-empty on success.
        model: The model identifier that produced `images`.
        latency_ms: Wall-clock time the request took, in milliseconds.
    """

    images: tuple[GeneratedImage, ...]
    model: str
    latency_ms: float


@dataclass(frozen=True)
class SpeechGenerationRequest:
    """A provider-independent request to generate spoken audio from text (EP-084).

    Only fields with a plausible, common meaning across text-to-speech
    APIs in general are included here -- provider-specific options
    belong in that provider's own `providers.<n>.*` configuration, not
    in this common contract (`EP084_DESIGN.md` Section 10), mirroring
    `ImageGenerationRequest`'s own restraint (EP-083).

    This dataclass performs no validation itself beyond the
    immutability a frozen dataclass gives for free. Each concrete
    `AIProvider.generate_speech()` implementation validates the fields
    it can actually honor and raises `ProviderConfigurationError` for
    anything it cannot -- the same layering `validate_temperature()`
    and `generate_image()` already established.

    Attributes:
        text: The text to speak. Required, non-empty.
        voice: A provider-defined voice name (e.g. "Kore"), or None to
            use the provider's own default voice.
        language: A best-effort language hint. Not every provider
            exposes a structured language parameter for speech
            generation (`EP084_DESIGN.md` Section 10) -- a provider
            without one may instead steer language via a natural-
            language instruction prepended to `text`. None means no
            hint is supplied.
        seed: Optional deterministic seed. None means no seed
            requested (provider default randomness).
    """

    text: str
    voice: str | None = None
    language: str | None = None
    seed: int | None = None


@dataclass(frozen=True)
class GeneratedAudio:
    """One generated audio clip (EP-084).

    In-memory only -- EP-084 introduces no file persistence
    (`EP084_DESIGN.md` Section 9/11), mirroring `GeneratedImage`
    (EP-083).

    Attributes:
        data_base64: The audio's bytes, base64-encoded. Per
            `EP084_DESIGN.md` Section 9 (Owner Decision D2), these
            bytes are a complete, directly playable WAV container --
            never raw/headerless PCM -- regardless of the raw format a
            provider's API itself returns.
        mime_type: The audio's MIME type. Always "audio/wav" per
            Owner Decision D2, independent of whatever MIME type the
            originating provider response reported.
    """

    data_base64: str
    mime_type: str


@dataclass(frozen=True)
class SpeechGenerationResult:
    """Result of a successful `AIProvider.generate_speech()` call (EP-084).

    Mirrors `ImageGenerationResult`'s shape, replacing the plural
    `images: tuple[GeneratedImage, ...]` with a singular
    `audio: GeneratedAudio` -- the provider API in scope for EP-084
    produces exactly one audio output per request, with no
    `number_of_images`-equivalent "how many outputs" request
    parameter (`EP084_DESIGN.md` Section 11).

    Attributes:
        audio: The generated audio.
        model: The model identifier that produced `audio`.
        latency_ms: Wall-clock time the request took, in milliseconds.
    """

    audio: GeneratedAudio
    model: str
    latency_ms: float


@dataclass(frozen=True)
class PingResult:
    """Result of an `AIProvider.ping()` connectivity check (EP-015).

    Attributes:
        reachable: Whether the provider's API could be reached.
        latency_ms: Round-trip time for the check, in milliseconds.
        model: The model identifier used for the check.
        authenticated: Whether the configured credentials were
            accepted. Only meaningful when `reachable` is True.
        message: Human-readable detail, especially on failure.
    """

    reachable: bool
    latency_ms: float
    model: str
    authenticated: bool
    message: str


@dataclass(frozen=True)
class ModelValidationResult:
    """Result of `AIProvider.validate_configured_model()` (EP-015.2 / EP-015.3).

    Shared return type for every provider's model-existence check, so
    AIService and the CLI can format the outcome of `ai use <provider>`
    identically regardless of which provider is active. Providers that
    can verify their configured model against a live model list (e.g.
    GeminiProvider, via ModelService.ListModels) override
    `validate_configured_model()` and return real values here; every
    other provider relies on `AIProvider`'s default implementation.

    Attributes:
        valid: Whether the configured model was confirmed usable.
        configured_model: The model this provider is configured to
            use, or "" if this provider does not expose one generically.
        available_models: Every model this provider confirmed is
            available, or an empty tuple if not (or not applicable).
        suggested_model: Closest available match by name, or None.
        message: Human-readable summary, especially on failure.
    """

    valid: bool
    configured_model: str
    available_models: tuple[str, ...]
    suggested_model: str | None
    message: str


class ProviderError(Exception):
    """Base class for errors raised while talking to an AI provider (EP-015)."""


class ProviderConfigurationError(ProviderError):
    """Raised when a provider is disabled or missing required configuration."""


class ProviderAuthenticationError(ProviderError):
    """Raised when a provider rejects the configured credentials."""


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds its configured timeout."""


class ProviderNetworkError(ProviderError):
    """Raised when a provider request fails due to a network problem."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider reports that a rate limit was exceeded."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is unreachable or refuses to serve a request."""


_MIN_TEMPERATURE: float = 0.0
_MAX_TEMPERATURE: float = 1.0


def validate_temperature(temperature: float | None) -> None:
    """Validate an optional per-request `temperature` override (EP-082).

    Single, shared validation rule applied identically by every
    concrete provider's `ask()` before translating a non-`None`
    `temperature` into that provider's own API call -- so no provider
    is free to interpret an invalid value differently
    (`EP082_DESIGN.md` Section 12.1). `AIProvider` is an ABC with no
    shared method body to validate inside `ask()` itself, so each
    concrete provider calls this function explicitly.

    Args:
        temperature: The caller-supplied override, or None (meaning
            "no override; preserve this provider's existing
            configured/default temperature behavior unchanged").

    Raises:
        ProviderConfigurationError: If `temperature` is not None and
            is not a real number in the inclusive 0.0-1.0 range.
    """
    if temperature is None:
        return
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ProviderConfigurationError(
            f"Invalid 'temperature' override: {temperature!r} is not a number."
        )
    if not (_MIN_TEMPERATURE <= float(temperature) <= _MAX_TEMPERATURE):
        raise ProviderConfigurationError(
            f"Invalid 'temperature' override: {temperature!r} is outside the valid "
            f"{_MIN_TEMPERATURE}-{_MAX_TEMPERATURE} range."
        )


class AIProvider(ABC):
    """Structural contract every AI provider must implement.

    Identity, configuration and health reporting (name/status/
    is_available/configuration/health) must never perform network
    requests (EP-014). `ask()`, `ping()` and `list_models()` are the
    EP-015 extension points for providers that DO implement real
    chat communication; their base implementations here are safe
    non-network no-ops so ProviderManager and the rest of Jarvis can
    treat any provider interchangeably without knowing which one is
    active.
    """

    @abstractmethod
    def name(self) -> str:
        """Return this provider's stable identifier (e.g. "ollama")."""
        raise NotImplementedError

    @abstractmethod
    def status(self) -> ProviderStatus:
        """Return this provider's current ProviderStatus."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether this provider is enabled and fully configured."""
        raise NotImplementedError

    @abstractmethod
    def configuration(self) -> dict[str, Any]:
        """Return a non-secret snapshot of this provider's configuration.

        Implementations must never include raw credentials (e.g. API
        keys) in the returned mapping, per this project's Logging
        Policy ("Never log secrets").
        """
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Return a configuration-derived readiness check.

        This is never a network connectivity check (EP-014 forbids
        network requests in this layer); it reflects whether this
        provider's own configuration looks usable.
        """
        raise NotImplementedError

    # ---------- EP-015: real communication extension points ----------

    def ask(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> ProviderResponse:
        """Send `prompt` to this provider and return its reply (EP-015).

        Base implementation always raises: this provider does not
        implement real chat communication. Providers that do (e.g.
        ClaudeProvider) must override this method.

        Args:
            prompt: The user prompt to send.
            max_tokens: Optional override for the reply's maximum
                token count. None uses the provider's configured
                default.
            temperature: Optional per-request override for this
                provider's creativity/randomness setting (EP-082).
                None means "no override; use this provider's existing
                configured/default temperature behavior unchanged" --
                it never means "force zero" or any other implicit
                value. When provided, must be a real number in the
                inclusive 0.0-1.0 range (`validate_temperature()`);
                an out-of-range value raises
                `ProviderConfigurationError`.
            system_prompt: Optional per-request system-prompt/style
                instruction override (EP-082). None means no
                per-request override is supplied; this provider's
                existing prompt-handling behavior is unchanged.

        Returns:
            The provider's reply.

        Raises:
            ProviderError: Always, unless overridden.
        """
        raise ProviderUnavailableError(
            f"Provider '{self.name()}' does not support chat requests."
        )

    def supports_image_generation(self) -> bool:
        """Return whether this provider instance can generate images (EP-083).

        Base implementation always returns False. This is a narrow,
        provider-level capability flag -- distinct from, and not a
        replacement for, EP-069.4's Unified Capability Abstraction
        (`src/core/capability/`), which catalogs external/internal
        tools and services, not AI-provider content modalities
        (`EP083_DESIGN.md` Section 6).

        Returns:
            True if `generate_image()` is meaningfully implemented by
            this provider (and configured), False otherwise.
        """
        return False

    def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate one or more images from `request` (EP-083).

        Base implementation always raises: this provider does not
        implement image generation. Providers that do (e.g.
        GeminiProvider, when configured with an image-capable model)
        must override this method and `supports_image_generation()`.

        Args:
            request: The provider-independent image-generation
                request.

        Returns:
            The provider's reply.

        Raises:
            ProviderError: Always, unless overridden.
        """
        raise ProviderUnavailableError(
            f"Provider '{self.name()}' does not support image generation."
        )

    def supports_speech_generation(self) -> bool:
        """Return whether this provider instance can generate speech (EP-084).

        Base implementation always returns False. This is a narrow,
        provider-level capability flag -- distinct from, and not a
        replacement for, EP-069.4's Unified Capability Abstraction
        (`src/core/capability/`), which catalogs external/internal
        tools and services, not AI-provider content modalities
        (`EP084_DESIGN.md` Section 3, mirroring `EP083_DESIGN.md`
        Section 6's own distinction for `supports_image_generation()`).

        Returns:
            True if `generate_speech()` is meaningfully implemented by
            this provider (and configured), False otherwise.
        """
        return False

    def generate_speech(self, request: SpeechGenerationRequest) -> SpeechGenerationResult:
        """Generate spoken audio from `request.text` (EP-084).

        Base implementation always raises: this provider does not
        implement speech generation. Providers that do (e.g.
        GeminiProvider, when configured with a TTS-capable model) must
        override this method and `supports_speech_generation()`.

        Args:
            request: The provider-independent speech-generation
                request.

        Returns:
            The provider's reply.

        Raises:
            ProviderError: Always, unless overridden.
        """
        raise ProviderUnavailableError(
            f"Provider '{self.name()}' does not support speech generation."
        )

    def ping(self) -> PingResult:
        """Check whether this provider is reachable and authenticated (EP-015).

        Base implementation performs no network request and reports
        this provider as unreachable. Providers that implement real
        communication (e.g. ClaudeProvider) should override this
        method with an actual connectivity check.
        """
        return PingResult(
            reachable=False,
            latency_ms=0.0,
            model="",
            authenticated=False,
            message=f"Provider '{self.name()}' does not support ping.",
        )

    def list_models(self) -> list[str]:
        """Return the models available to this provider (EP-015).

        Never performs online discovery; models are read from this
        provider's own configuration. Base implementation returns an
        empty list.
        """
        return []

    def validate_configured_model(self) -> ModelValidationResult:
        """Verify this provider's configured model is usable (EP-015.2 / EP-015.3).

        Called by `AIService.use_provider()` immediately after
        `ai use <provider>` selects this provider, so problems surface
        right away instead of on the next `ask()`. Base implementation
        performs no per-model check (it has no generic way to know
        which model a provider is configured for) and instead falls
        back to this provider's own configuration-derived `health()`
        check -- never a network request. Providers that can confirm
        their configured model against a live model list (e.g.
        GeminiProvider, via ModelService.ListModels) should override
        this method with a real check.

        Returns:
            A ModelValidationResult: `valid` mirrors `health().available`;
            `configured_model` is "" since the base class has no
            generic concept of a single configured model name.
        """
        healthy = self.health()
        if not healthy.available:
            return ModelValidationResult(
                valid=False,
                configured_model="",
                available_models=(),
                suggested_model=None,
                message=healthy.message,
            )
        return ModelValidationResult(
            valid=True,
            configured_model="",
            available_models=(),
            suggested_model=None,
            message=f"Provider '{self.name()}' does not implement model-level validation.",
        )
