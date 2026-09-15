"""Concrete EP-092 PersonalDataSource implementations for EP-093.

Electricity & Gas Monitoring (EP-093) consumes EP-092's Personal Data
Collection Framework exclusively through the existing
`PersonalDataSource` contract (`src/core/personal_data/
personal_data_source.py`) -- no second acquisition-provider
abstraction is introduced (STEP 1 design §6.2, Design A). Each
acquisition mechanism is its own concrete `PersonalDataSource`
subclass, living in this package, never inside EP-092's own
`src/core/personal_data/` package.

V1 (this package): manual entry + CSV import for electricity and gas
consumption, per `docs/architecture/designs/EP093_DESIGN.md` §6.3-6.4.
A future named vendor/API (§6.6) would be one more module in this
same package, with no change required anywhere else.
"""

from __future__ import annotations

from src.core.personal_data.sources.electricity_source import (
    CATEGORY as ELECTRICITY_CATEGORY,
)
from src.core.personal_data.sources.electricity_source import (
    SOURCE_ID as ELECTRICITY_SOURCE_ID,
)
from src.core.personal_data.sources.electricity_source import (
    ElectricityCsvSource,
    append_electricity_reading,
    import_electricity_csv,
)
from src.core.personal_data.sources.gas_source import CATEGORY as GAS_CATEGORY
from src.core.personal_data.sources.gas_source import SOURCE_ID as GAS_SOURCE_ID
from src.core.personal_data.sources.gas_source import (
    GasCsvSource,
    append_gas_reading,
    import_gas_csv,
)

__all__ = [
    "ElectricityCsvSource",
    "append_electricity_reading",
    "import_electricity_csv",
    "ELECTRICITY_CATEGORY",
    "ELECTRICITY_SOURCE_ID",
    "GasCsvSource",
    "append_gas_reading",
    "import_gas_csv",
    "GAS_CATEGORY",
    "GAS_SOURCE_ID",
]
