/**
 * EP-045 Web Dashboard — client-side logic.
 *
 * Plain JavaScript, no framework, no build step, matching the
 * technology decision in docs/architecture/designs/EP045_DESIGN.md,
 * Section 9. Talks to the EP-043 REST API using same-origin, relative
 * URLs only ("/health", "/api/v1/status", "/api/v1/commands") --
 * because the dashboard and the API are served from the exact same
 * origin (Section 21, "Option A"), no API base URL / host / port
 * configuration is needed here at all. This is a direct, documented
 * consequence of the owner's same-origin decision, not an
 * independent choice made by this file.
 *
 * Mirrors EP-044's Desktop UI client (desktop/api/jarvis_api_client.py)
 * conceptually (see EP045_DESIGN.md Section 5.1): same timeout policy,
 * same "success:false still means HTTP 200" rule, same typed error
 * categories, no automatic retries.
 */

(() => {
  "use strict";

  // EP045_DESIGN.md Section 12: mirrors EP-044's own resolved
  // DEFAULT_TIMEOUT_SECONDS = 10.0 for consistency across Jarvis's two
  // existing REST clients (Open Question 7, proposed default).
  const REQUEST_TIMEOUT_MS = 10_000;

  // ---- DOM references ----

  const connectionIndicator = document.getElementById("connection-indicator");
  const connectionLabel = document.getElementById("connection-label");
  const reconnectButton = document.getElementById("reconnect-button");

  const statusLine = document.getElementById("status-line");
  const refreshStatusButton = document.getElementById("refresh-status-button");

  const commandForm = document.getElementById("command-form");
  const moduleInput = document.getElementById("module-input");
  const actionInput = document.getElementById("action-input");
  const argumentsInput = document.getElementById("arguments-input");
  const executeButton = document.getElementById("execute-button");

  const resultPane = document.getElementById("result-pane");

  const errorCard = document.getElementById("error-card");
  const errorLine = document.getElementById("error-line");
  const dismissErrorButton = document.getElementById("dismiss-error-button");

  // ---- Error categories (EP045_DESIGN.md Section 14) ----
  //
  // Distinct categories, distinct messages -- never collapsed into one
  // generic string, and never a raw stack trace shown to the user.

  class NetworkError extends Error {}
  class TimeoutError extends Error {}
  class HttpError extends Error {
    constructor(status, code, message) {
      super(message);
      this.status = status;
      this.code = code;
    }
  }
  class MalformedResponseError extends Error {}

  /**
   * Perform a same-origin fetch with an explicit timeout and no
   * automatic retries (EP045_DESIGN.md Section 12 -- POST
   * /api/v1/commands may have side effects, so a failed/timed-out
   * request must not be silently retried).
   */
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    let response;
    try {
      response = await fetch(path, { ...options, signal: controller.signal });
    } catch (error) {
      if (error.name === "AbortError") {
        throw new TimeoutError("Request timed out.");
      }
      // A browser fetch() rejection here also covers a same-origin
      // CORS/misconfiguration failure, which is indistinguishable
      // from "server unreachable" -- see EP045_DESIGN.md Section 14.
      throw new NetworkError("Cannot reach Jarvis.");
    } finally {
      clearTimeout(timer);
    }

    let body;
    const text = await response.text();
    try {
      body = text ? JSON.parse(text) : {};
    } catch {
      throw new MalformedResponseError("Unexpected response from Jarvis.");
    }

    if (!response.ok) {
      const errorPayload = body && body.error ? body.error : {};
      throw new HttpError(
        response.status,
        errorPayload.code || "unknown_error",
        errorPayload.message || `Request failed with status ${response.status}.`
      );
    }

    return body;
  }

  // ---- Connection state (EP045_DESIGN.md Section 13) ----

  function setConnectionState(state, label) {
    connectionIndicator.dataset.state = state;
    connectionLabel.textContent = label;
  }

  async function checkConnection() {
    setConnectionState("connecting", "Connecting\u2026");
    try {
      const health = await request("/health");
      if (health && health.status === "ok") {
        setConnectionState("connected", "Connected");
      } else {
        setConnectionState("api_unavailable", "Unexpected response from /health");
      }
    } catch (error) {
      setConnectionState(
        error instanceof TimeoutError ? "api_unavailable" : "disconnected",
        describeError(error)
      );
    }
  }

  // ---- Status area ----

  async function refreshStatus() {
    statusLine.textContent = "Loading\u2026";
    try {
      const status = await request("/api/v1/status");
      statusLine.textContent = status.message || "(no message)";
    } catch (error) {
      statusLine.textContent = "Unable to load status.";
      showError(error);
    }
  }

  // ---- Command execution ----

  function parseArguments(raw) {
    const trimmed = raw.trim();
    if (!trimmed) return [];
    return trimmed.split(/\s+/);
  }

  async function executeCommand(event) {
    event.preventDefault();

    const moduleValue = moduleInput.value.trim();
    if (!moduleValue) {
      moduleInput.reportValidity();
      return;
    }

    const payload = {
      module: moduleValue,
      action: actionInput.value.trim(),
      arguments: parseArguments(argumentsInput.value),
    };

    executeButton.disabled = true;
    executeButton.textContent = "Running\u2026";
    hideError();

    try {
      const result = await request("/api/v1/commands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      // EP045_DESIGN.md Section 12: "success: false" still means HTTP
      // 200 -- branch on the body's `success` field, not the status.
      resultPane.dataset.empty = "false";
      resultPane.dataset.success = String(Boolean(result.success));
      resultPane.textContent = result.message || "(no message)";
    } catch (error) {
      showError(error);
    } finally {
      executeButton.disabled = false;
      executeButton.textContent = "Execute";
    }
  }

  // ---- Error area ----

  function describeError(error) {
    if (error instanceof TimeoutError) return "Request timed out.";
    if (error instanceof NetworkError) return "Cannot reach Jarvis.";
    if (error instanceof MalformedResponseError) return "Unexpected response from Jarvis.";
    if (error instanceof HttpError) return error.message;
    return "Something went wrong.";
  }

  function showError(error) {
    errorLine.textContent = describeError(error);
    errorCard.hidden = false;
  }

  function hideError() {
    errorCard.hidden = true;
    errorLine.textContent = "";
  }

  // ---- Wiring ----

  reconnectButton.addEventListener("click", checkConnection);
  refreshStatusButton.addEventListener("click", refreshStatus);
  commandForm.addEventListener("submit", executeCommand);
  dismissErrorButton.addEventListener("click", hideError);

  // Initial load: check connection and status once, matching
  // EP045_DESIGN.md's "manual-only" default (Open Question 6) --
  // no periodic polling in V1.
  checkConnection();
  refreshStatus();
})();
