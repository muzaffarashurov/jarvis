"""Personal data package: EP-092 Personal Data Collection Framework.

Personal Data Collection is responsible for domain-agnostic ingestion
of "permitted personal operational data" -- structured, externally
observed measurements arriving repeatedly over time (a utility API, a
solar-inverter API, a weather API, a manual entry). It performs no
electricity/gas/solar/weather-specific logic, no visualization,
reporting, forecasting, anomaly detection, or recommendations (those
belong to EP-093-098), and has no dependency on Embedding, Retrieval,
RAG, Semantic Search, Context Compression, or Knowledge Base.

`PersonalDataPoint` (`personal_data_record.py`) is the plain data
model for a single collected measurement. `PersonalDataSource`
(`personal_data_source.py`) is the domain-agnostic contract EP-093/
094/097 implement. `PersonalDataProvider` / `JsonlPersonalDataProvider`
(`personal_data_provider.py`) define the storage contract and its
sole approved implementation (Owner Decision, STEP 1 design §21:
dedicated append-only JSONL, not Knowledge Base), delegating raw file
I/O to `PersonalDataPersistence` (`personal_data_persistence.py`).
`PersonalDataRegistry` (`personal_data_registry.py`) registers sources
by `source_id`. `PersonalDataManager` /
`PersonalDataCollectionError` (`personal_data_manager.py`) orchestrate
one collection cycle (collect -> consent-gate -> dedupe -> persist)
and the read-side query surface.

Public API:
    PersonalDataPoint -- A single collected measurement.
    PersonalDataSource -- The domain-agnostic source contract.
    PersonalDataProvider / PersonalDataProviderError -- The storage contract.
    JsonlPersonalDataProvider -- The approved concrete provider (Owner Decision, §21).
    PersonalDataPersistence / PersonalDataPersistenceError -- Low-level JSONL file I/O
        (used only by JsonlPersonalDataProvider), including category-name validation
        (STEP 3 audit finding EP092-AUDIT-001).
    PersonalDataRegistry / PersonalDataRegistryError -- Source registration.
    PersonalDataManager / PersonalDataCollectionError -- The orchestration layer.
"""

from __future__ import annotations

from src.core.personal_data.personal_data_manager import (
    PersonalDataCollectionError,
    PersonalDataManager,
)
from src.core.personal_data.personal_data_persistence import (
    PersonalDataPersistence,
    PersonalDataPersistenceError,
)
from src.core.personal_data.personal_data_provider import (
    JsonlPersonalDataProvider,
    PersonalDataProvider,
    PersonalDataProviderError,
)
from src.core.personal_data.personal_data_record import PersonalDataPoint
from src.core.personal_data.personal_data_registry import (
    PersonalDataRegistry,
    PersonalDataRegistryError,
)
from src.core.personal_data.personal_data_source import PersonalDataSource

__all__ = [
    "PersonalDataPoint",
    "PersonalDataSource",
    "PersonalDataProvider",
    "PersonalDataProviderError",
    "JsonlPersonalDataProvider",
    "PersonalDataPersistence",
    "PersonalDataPersistenceError",
    "PersonalDataRegistry",
    "PersonalDataRegistryError",
    "PersonalDataManager",
    "PersonalDataCollectionError",
]
