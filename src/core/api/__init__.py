"""EP-043 REST API core package.

Contains the REST API's transport-agnostic building blocks:

- ``api_error``: the API's error hierarchy (maps to HTTP status codes).
- ``dto``: request/response DTOs defining the API's external JSON
  contract, independent of any internal Jarvis domain object.
- ``api_router``: ``ApiRouter``, the thin bridge from a
  (module, action, arguments) triple to the existing, shared
  ``CommandRouter`` -- the exact same entry point ``InteractiveShell``
  and ``TelegramRouter`` already dispatch through.
- ``rest_api_server``: ``RestApiServer``, the stdlib-``http.server``
  HTTP transport that turns real HTTP requests into ``ApiRouter``
  calls.

No module in this package contains business logic. All business
behaviour lives in the existing Core/Service/Module layers, which this
package only adapts to HTTP.
"""

from __future__ import annotations
