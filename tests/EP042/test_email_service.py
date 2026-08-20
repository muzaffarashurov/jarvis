"""Real engineering tests for EP-042 STEP 2 - EmailService.

Builds a real EmailService with a small, duck-typed stub `connection`
object standing in for `imaplib.IMAP4_SSL`/`IMAP4` -- no real IMAP
server is ever contacted anywhere in this suite. The configured
credential environment variables are set/unset directly via
`os.environ` around each test that needs them, always restored
afterward, so this suite never depends on (or leaks into) the real
process environment beyond the duration of a single test.
"""

from __future__ import annotations

import imaplib
import os
import socket
import ssl
import tempfile
from email.message import EmailMessage as StdlibEmailMessage
from pathlib import Path

from src.core.config import Config
from src.core.email.email_error import (
    EmailAuthenticationError,
    EmailConnectionError,
    EmailMailboxError,
    EmailMessageNotFoundError,
    EmailProtocolError,
    EmailSearchError,
    EmailTLSError,
    EmailTimeoutError,
)
from src.services.email_service import EmailService, EmailServiceError
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_USERNAME_ENV_VAR = "EMAIL_IMAP_USERNAME"
_PASSWORD_ENV_VAR = "EMAIL_IMAP_PASSWORD"
_FAKE_USERNAME = "fake-user@example.com"
_FAKE_PASSWORD = "fake-password-for-tests-xyz123"


class _CredentialGuard:
    """Context manager: set the two credential env vars for the
    duration of a `with` block (or unset them entirely if a value is
    None), always restoring whatever was present before."""

    def __init__(self, username: str | None, password: str | None) -> None:
        self._username = username
        self._password = password
        self._original: dict[str, str | None] = {}
        self._was_set: dict[str, bool] = {}

    def __enter__(self) -> None:
        for var, value in ((_USERNAME_ENV_VAR, self._username), (_PASSWORD_ENV_VAR, self._password)):
            self._was_set[var] = var in os.environ
            self._original[var] = os.environ.get(var)
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        for var in (_USERNAME_ENV_VAR, _PASSWORD_ENV_VAR):
            if self._was_set[var]:
                os.environ[var] = self._original[var]
            else:
                os.environ.pop(var, None)


class _StubConnection:
    """A minimal duck-typed stand-in for `imaplib.IMAP4_SSL`/`IMAP4`.

    Every constructor argument scripts one call's response (or
    exception). Records every call made so tests can assert a call
    did/did not happen and inspect its arguments.
    """

    def __init__(
        self,
        *,
        login_exception: Exception | None = None,
        select_result: tuple = ("OK", [b"1"]),
        list_result: tuple = ("OK", [b'(\\HasNoChildren) "." "INBOX"']),
        search_result: tuple = ("OK", [b""]),
        search_exception: Exception | None = None,
        fetch_results: dict | None = None,
        fetch_exception: Exception | None = None,
    ) -> None:
        self.login_exception = login_exception
        self.select_result = select_result
        self.list_result = list_result
        self.search_result = search_result
        self.search_exception = search_exception
        self.fetch_results = fetch_results or {}
        self.fetch_exception = fetch_exception
        self.calls: list[tuple] = []

    def login(self, user, password):
        self.calls.append(("login", user, password))
        if self.login_exception is not None:
            raise self.login_exception
        return ("OK", [b"Logged in"])

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return self.select_result

    def list(self):
        self.calls.append(("list",))
        return self.list_result

    def uid(self, command, *args):
        self.calls.append(("uid", command, args))
        if command == "search":
            if self.search_exception is not None:
                raise self.search_exception
            return self.search_result
        if command == "fetch":
            if self.fetch_exception is not None:
                raise self.fetch_exception
            uid_arg = args[0]
            return self.fetch_results.get(uid_arg, ("OK", []))
        raise ValueError(f"Unexpected uid command: {command!r}")

    def close(self):
        self.calls.append(("close",))
        return ("OK", [None])

    def logout(self):
        self.calls.append(("logout",))
        return ("OK", [b"BYE"])


def _write_config(directory: Path, sections: str) -> Config:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


def _default_config(tmp: str) -> Config:
    return _write_config(
        Path(tmp),
        (
            "email:\n"
            "  enabled: true\n"
            '  imap_host: "imap.example.com"\n'
            "  imap_port: 993\n"
            '  tls_mode: "ssl"\n'
            "  default_mailbox: \"INBOX\"\n"
            "  default_message_limit: 50\n"
            "  timeout_seconds: 30\n"
        ),
    )


def _build_simple_message_bytes(uid_marker: str = "1") -> bytes:
    msg = StdlibEmailMessage()
    msg["Subject"] = f"Test subject {uid_marker}"
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "bob@example.com, carol@example.com"
    msg["Date"] = "Mon, 19 Aug 2026 10:00:00 +0000"
    msg["Message-ID"] = f"<{uid_marker}@example.com>"
    msg.set_content("Hello, this is the body.")
    return msg.as_bytes()


def _build_multipart_message_with_attachment_bytes() -> bytes:
    msg = StdlibEmailMessage()
    msg["Subject"] = "Message with attachment"
    msg["From"] = "Dave <dave@example.com>"
    msg["To"] = "eve@example.com"
    msg["Date"] = "Mon, 19 Aug 2026 11:00:00 +0000"
    msg.set_content("Plain text body.")
    msg.add_alternative("<p>HTML body.</p>", subtype="html")
    msg.add_attachment(b"PDF-DATA-HERE", maintype="application", subtype="pdf", filename="report.pdf")
    return msg.as_bytes()


@TestRegistry.register
class EmailServiceTest(BaseTest):
    NAME = "EP042"

    def run(self):
        self._test_list_folders_success()
        self._test_list_messages_success()
        self._test_get_message_success()
        self._test_get_message_multipart_with_attachment()
        self._test_search_messages_success()
        self._test_search_empty_result()
        self._test_search_rejected_criteria()
        self._test_search_blank_criteria_raises()

        self._test_missing_username_raises_and_never_connects()
        self._test_missing_password_raises()
        self._test_blank_username_raises()
        self._test_login_rejected_raises_authentication_error()

        self._test_connection_timeout_raises_timeout_error()
        self._test_connection_tls_error_raises_tls_error()
        self._test_connection_refused_raises_connection_error()
        self._test_login_timeout_raises_timeout_error()

        self._test_select_failure_raises_mailbox_error()
        self._test_message_not_found_raises()
        self._test_malformed_list_response_raises_protocol_error()

        self._test_construction_rejects_missing_host_when_enabled()
        self._test_construction_rejects_invalid_port()
        self._test_construction_rejects_invalid_tls_mode()
        self._test_construction_rejects_invalid_timeout()
        self._test_construction_defaults_applied()

        self._test_credentials_never_leak_into_exception_messages()
        self._test_select_always_readonly()
        self._test_logout_called_after_every_operation()

        # STEP 3 audit: regression coverage for defects found and fixed
        # during the EP042 STEP 3 audit (see EP042_DESIGN.md addendum).
        self._test_malformed_charset_in_body_does_not_crash()
        self._test_malformed_charset_in_header_does_not_crash()
        self._test_to_cc_headers_are_rfc2047_decoded()
        self._test_list_messages_orders_by_uid_not_server_order()

        return self.result

    # ---------- Successful operations ----------

    def _test_list_folders_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(
                list_result=(
                    "OK",
                    [
                        b'(\\HasNoChildren) "." "INBOX"',
                        b'(\\HasChildren) "." "Archive"',
                    ],
                )
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.list_folders()
            self.assert_equal(len(result.data), 2)
            self.assert_equal(result.data[0].name, "INBOX")
            self.assert_equal(result.data[1].name, "Archive")
            self.assert_equal(result.operation, "list_folders")

    def _test_list_messages_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(
                search_result=("OK", [b"1 2 3"]),
                fetch_results={
                    "3": ("OK", [(b"3 (BODY[HEADER] {10}", _build_simple_message_bytes("3"))]),
                    "2": ("OK", [(b"2 (BODY[HEADER] {10}", _build_simple_message_bytes("2"))]),
                    "1": ("OK", [(b"1 (BODY[HEADER] {10}", _build_simple_message_bytes("1"))]),
                },
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.list_messages(folder="INBOX", limit=2)
            # Most recent first -> uid 3, then uid 2 (uid 1 excluded by limit)
            self.assert_equal(len(result.data), 2)
            self.assert_equal(result.data[0].uid, "3")
            self.assert_equal(result.data[1].uid, "2")
            self.assert_equal(result.data[0].subject, "Test subject 3")

    def _test_get_message_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(
                fetch_results={
                    "42": ("OK", [(b"42 (RFC822 {10}", _build_simple_message_bytes("42"))]),
                },
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.get_message("INBOX", "42")
            message = result.data
            self.assert_equal(message.uid, "42")
            self.assert_equal(message.subject, "Test subject 42")
            self.assert_equal(message.sender, "Alice <alice@example.com>")
            self.assert_equal(message.recipients, ("bob@example.com", "carol@example.com"))
            self.assert_true("Hello, this is the body." in (message.body_text or ""))

    def _test_get_message_multipart_with_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(
                fetch_results={
                    "7": (
                        "OK",
                        [(b"7 (RFC822 {10}", _build_multipart_message_with_attachment_bytes())],
                    ),
                },
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.get_message("INBOX", "7")
            message = result.data
            self.assert_true("Plain text body." in (message.body_text or ""))
            self.assert_true("HTML body." in (message.body_html or ""))
            self.assert_equal(len(message.attachments), 1)
            self.assert_equal(message.attachments[0].filename, "report.pdf")
            self.assert_equal(message.attachments[0].content_type, "application/pdf")
            self.assert_true(message.attachments[0].size_bytes > 0)

    def _test_search_messages_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(
                search_result=("OK", [b"5 6"]),
                fetch_results={
                    "5": ("OK", [(b"5 (BODY[HEADER] {10}", _build_simple_message_bytes("5"))]),
                    "6": ("OK", [(b"6 (BODY[HEADER] {10}", _build_simple_message_bytes("6"))]),
                },
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.search_messages("INBOX", 'SUBJECT "Test"')
            self.assert_equal(len(result.data), 2)
            search_calls = [c for c in connection.calls if c[0] == "uid" and c[1] == "search"]
            self.assert_equal(len(search_calls), 1)
            self.assert_equal(search_calls[0][2], (None, 'SUBJECT "Test"'))

    def _test_search_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(search_result=("OK", [b""]))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.search_messages("INBOX", "UNSEEN")
            self.assert_equal(result.data, [])

    def _test_search_rejected_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(search_exception=imaplib.IMAP4.error("bad criteria"))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.search_messages("INBOX", "NOT-A-REAL-CRITERIA")
                    self.assert_true(False, "invalid criteria should have raised")
                except EmailSearchError:
                    self.result.add_pass()

    def _test_search_blank_criteria_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection()
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.search_messages("INBOX", "   ")
                    self.assert_true(False, "blank criteria should have raised")
                except EmailSearchError:
                    self.result.add_pass()

    # ---------- Authentication ----------

    def _test_missing_username_raises_and_never_connects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection()
            factory_calls = []

            def factory(*args):
                factory_calls.append(args)
                return connection

            service = EmailService(config=config, connection_factory=factory)
            with _CredentialGuard(None, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "missing username should have raised")
                except EmailAuthenticationError:
                    self.result.add_pass()
            self.assert_equal(len(factory_calls), 0, "no connection should be opened without credentials")

    def _test_missing_password_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection()
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, None):
                try:
                    service.list_folders()
                    self.assert_true(False, "missing password should have raised")
                except EmailAuthenticationError:
                    self.result.add_pass()

    def _test_blank_username_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection()
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard("   ", _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "blank username should have raised")
                except EmailAuthenticationError:
                    self.result.add_pass()

    def _test_login_rejected_raises_authentication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(login_exception=imaplib.IMAP4.error("LOGIN failed"))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "rejected login should have raised")
                except EmailAuthenticationError:
                    self.result.add_pass()

    # ---------- Connection ----------

    def _test_connection_timeout_raises_timeout_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)

            def failing_factory(*args):
                raise socket.timeout("timed out")

            service = EmailService(config=config, connection_factory=failing_factory)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "connection timeout should have raised")
                except EmailTimeoutError:
                    self.result.add_pass()

    def _test_connection_tls_error_raises_tls_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)

            def failing_factory(*args):
                raise ssl.SSLError("certificate verify failed")

            service = EmailService(config=config, connection_factory=failing_factory)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "TLS failure should have raised")
                except EmailTLSError:
                    self.result.add_pass()

    def _test_connection_refused_raises_connection_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)

            def failing_factory(*args):
                raise ConnectionRefusedError("connection refused")

            service = EmailService(config=config, connection_factory=failing_factory)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "connection refusal should have raised")
                except EmailConnectionError:
                    self.result.add_pass()

    def _test_login_timeout_raises_timeout_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(login_exception=socket.timeout("timed out"))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "login timeout should have raised")
                except EmailTimeoutError:
                    self.result.add_pass()

    # ---------- Mailboxes / messages ----------

    def _test_select_failure_raises_mailbox_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(select_result=("NO", [b"Mailbox does not exist"]))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_messages(folder="DoesNotExist")
                    self.assert_true(False, "select failure should have raised")
                except EmailMailboxError:
                    self.result.add_pass()

    def _test_message_not_found_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(fetch_results={})
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.get_message("INBOX", "9999")
                    self.assert_true(False, "missing uid should have raised")
                except EmailMessageNotFoundError:
                    self.result.add_pass()

    def _test_malformed_list_response_raises_protocol_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(list_result=("OK", [b"not a valid LIST line"]))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "malformed response should have raised")
                except EmailProtocolError:
                    self.result.add_pass()

    # ---------- Construction / configuration ----------

    def _test_construction_rejects_missing_host_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), 'email:\n  enabled: true\n  imap_host: ""\n')
            try:
                EmailService(config=config)
                self.assert_true(False, "missing host should have raised")
            except EmailServiceError:
                self.result.add_pass()

    def _test_construction_rejects_invalid_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                'email:\n  enabled: true\n  imap_host: "imap.example.com"\n  imap_port: 0\n',
            )
            try:
                EmailService(config=config)
                self.assert_true(False, "invalid port should have raised")
            except EmailServiceError:
                self.result.add_pass()

    def _test_construction_rejects_invalid_tls_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                'email:\n  enabled: true\n  imap_host: "imap.example.com"\n  tls_mode: "plaintext"\n',
            )
            try:
                EmailService(config=config)
                self.assert_true(False, "invalid tls_mode should have raised")
            except EmailServiceError:
                self.result.add_pass()

    def _test_construction_rejects_invalid_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                'email:\n  enabled: true\n  imap_host: "imap.example.com"\n  timeout_seconds: -1\n',
            )
            try:
                EmailService(config=config)
                self.assert_true(False, "invalid timeout should have raised")
            except EmailServiceError:
                self.result.add_pass()

    def _test_construction_defaults_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # 'enabled' omitted (defaults to false) -> imap_host may be blank without raising.
            config = _write_config(Path(tmp), "email:\n  enabled: false\n")
            service = EmailService(config=config, connection_factory=lambda *a: _StubConnection())
            self.assert_equal(service._imap_port, 993)
            self.assert_equal(service._tls_mode, "ssl")
            self.assert_equal(service._default_mailbox, "INBOX")
            self.assert_equal(service._default_message_limit, 50)

    # ---------- Security ----------

    def _test_credentials_never_leak_into_exception_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(login_exception=imaplib.IMAP4.error("LOGIN failed"))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                try:
                    service.list_folders()
                    self.assert_true(False, "rejected login should have raised")
                except EmailAuthenticationError as exc:
                    message = str(exc)
                    self.assert_true(_FAKE_PASSWORD not in message)
                    self.assert_true(_FAKE_USERNAME not in message)

    def _test_select_always_readonly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(search_result=("OK", [b""]))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                service.list_messages(folder="INBOX", limit=5)
            select_calls = [c for c in connection.calls if c[0] == "select"]
            self.assert_equal(len(select_calls), 1)
            self.assert_equal(select_calls[0][2], True)

    def _test_logout_called_after_every_operation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            connection = _StubConnection(search_result=("OK", [b""]))
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                service.list_messages(folder="INBOX", limit=5)
            logout_calls = [c for c in connection.calls if c[0] == "logout"]
            self.assert_equal(len(logout_calls), 1)

    # ---------- STEP 3 audit regression coverage ----------

    def _test_malformed_charset_in_body_does_not_crash(self) -> None:
        """A body part declaring an unrecognized charset (e.g. a
        garbled/nonstandard charset name from a malformed sender) must
        be decoded on a best-effort basis, not raise a bare
        LookupError/UnicodeDecodeError out of get_message()."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            msg = StdlibEmailMessage()
            msg["Subject"] = "Malformed charset body"
            msg["From"] = "weird@example.com"
            msg.set_content("Hello, this is the body.")
            msg.set_param("charset", "x-bogus-charset-name", header="Content-Type")
            connection = _StubConnection(
                fetch_results={"1": ("OK", [(b"1 (RFC822 {1}", msg.as_bytes())])},
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.get_message("INBOX", "1")
            # Must not raise, and must still contain a best-effort-decoded body.
            self.assert_true("Hello, this is the body." in (result.data.body_text or ""))

    def _test_malformed_charset_in_header_does_not_crash(self) -> None:
        """A Subject header containing an RFC 2047 encoded-word with an
        unrecognized charset must be decoded on a best-effort basis,
        not raise out of list_messages()/get_message()."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            msg = StdlibEmailMessage()
            msg["Subject"] = "=?x-bogus-charset-name?B?aGVsbG8=?="
            msg["From"] = "weird@example.com"
            msg.set_content("body")
            connection = _StubConnection(
                search_result=("OK", [b"1"]),
                fetch_results={
                    "1": ("OK", [(b"1 (BODY[HEADER] {1}", msg.as_bytes())]),
                },
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.list_messages(folder="INBOX", limit=5)
            # Must not raise; the decoded subject should contain the
            # best-effort-decoded bytes rather than crashing.
            self.assert_equal(len(result.data), 1)

    def _test_to_cc_headers_are_rfc2047_decoded(self) -> None:
        """The design (EP042_DESIGN.md section 15) explicitly requires
        To/Cc headers to be RFC 2047-decoded the same way Subject/From
        are -- not just comma-split."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            msg = StdlibEmailMessage()
            msg["Subject"] = "Encoded recipient name"
            msg["From"] = "sender@example.com"
            # "=?utf-8?b?Sm9zw6k=?=" decodes to "José"
            msg["To"] = '=?utf-8?b?Sm9zw6k=?= <jose@example.com>, plain@example.com'
            msg.set_content("body")
            connection = _StubConnection(
                fetch_results={"1": ("OK", [(b"1 (RFC822 {1}", msg.as_bytes())])},
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.get_message("INBOX", "1")
            recipients = result.data.recipients
            self.assert_equal(len(recipients), 2)
            self.assert_true(any("José" in r for r in recipients))

    def _test_list_messages_orders_by_uid_not_server_order(self) -> None:
        """list_messages must order by UID value itself, not merely by
        whatever order the server happened to return SEARCH results
        in (RFC 3501 does not guarantee SEARCH result order)."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            # Server intentionally returns UIDs out of numeric order.
            connection = _StubConnection(
                search_result=("OK", [b"10 2 30 1"]),
                fetch_results={
                    "1": ("OK", [(b"1 (BODY[HEADER] {1}", _build_simple_message_bytes("1"))]),
                    "2": ("OK", [(b"2 (BODY[HEADER] {1}", _build_simple_message_bytes("2"))]),
                    "10": ("OK", [(b"10 (BODY[HEADER] {1}", _build_simple_message_bytes("10"))]),
                    "30": ("OK", [(b"30 (BODY[HEADER] {1}", _build_simple_message_bytes("30"))]),
                },
            )
            service = EmailService(config=config, connection_factory=lambda *a: connection)
            with _CredentialGuard(_FAKE_USERNAME, _FAKE_PASSWORD):
                result = service.list_messages(folder="INBOX", limit=2)
            # Numerically ascending order is [1, 2, 10, 30]; the two
            # most recent (highest UID) are 30 and 10, newest first.
            self.assert_equal([m.uid for m in result.data], ["30", "10"])
