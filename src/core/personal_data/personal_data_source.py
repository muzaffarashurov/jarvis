"""Source contract for EP-092 Personal Data Collection Framework.

`PersonalDataSource` is the domain-agnostic contract EP-093
(Electricity & Gas), EP-094 (Solar), and EP-097 (Weather) each
implement, without this module knowing anything about any of them.
`PersonalDataManager` (via `PersonalDataRegistry`) is the only
component that calls `collect()`; a source never touches
`PersonalDataProvider`, `PersonalDataPersistence`, or `CommandResult`
directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.personal_data.personal_data_record import PersonalDataPoint


class PersonalDataSource(ABC):
    """Unified interface implemented by every personal-data source.

    A concrete source (a utility API client, a solar-inverter API
    client, a weather API client, a manual/CSV-style source) is
    responsible only for producing `PersonalDataPoint` instances. It
    never stores, deduplicates, or filters them -- that is
    `PersonalDataManager`'s job.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Return this source's unique registration identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def category(self) -> str:
        """Return the personal-data category this source produces."""
        raise NotImplementedError

    @abstractmethod
    def collect(self) -> list[PersonalDataPoint]:
        """Return newly observed points since the last call.

        Returns an empty list when there is nothing new -- this is
        the normal, expected outcome of a call that succeeded but
        found no new data, and is not an error.

        May raise an exception when collection itself fails (e.g. a
        transient network error, an unreachable API, a malformed
        response). A source must let such a failure propagate rather
        than silently swallowing it inside `collect()` -- swallowing
        would hide the failure from the collection boundary below.

        The source is never responsible for containing that failure:
        `PersonalDataManager.collect_from()` is the collection
        boundary. It catches any exception `collect()` raises, so the
        failure never escapes to crash the Scheduler tick, and
        re-raises it as `PersonalDataCollectionError`
        (`personal_data_manager.py`).

        Returns:
            Newly observed `PersonalDataPoint` instances, or an empty
            list if there is nothing new.

        Raises:
            Exception: Any exception representing a collection
                failure. `PersonalDataManager` is the only caller and
                treats any raised exception uniformly.
        """
        raise NotImplementedError
