"""Simple synchronous publish/subscribe event bus for Jarvis."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from loguru import logger

EventHandler = Callable[..., None]


class EventBus:
    """A minimal synchronous publish/subscribe event bus.

    Responsibilities:
        - Allow components to subscribe callbacks to named events.
        - Allow components to publish events, invoking all subscribers.
        - Isolate subscriber failures so one bad handler cannot break
          the publishing flow.
    """

    def __init__(self) -> None:
        """Initialize an empty EventBus with no subscribers."""
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register a handler for a named event.

        Args:
            event_name: The name of the event to subscribe to.
            handler: A callable invoked when the event is published.

        Raises:
            ValueError: If `event_name` is empty.
            TypeError: If `handler` is not callable.
        """
        if not event_name:
            raise ValueError("event_name must be a non-empty string.")
        if not callable(handler):
            raise TypeError(f"Handler for event '{event_name}' must be callable.")

        self._subscribers[event_name].append(handler)
        handler_name = getattr(handler, "__name__", repr(handler))
        logger.debug(f"Subscribed handler '{handler_name}' to event '{event_name}'")

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """Remove a previously registered handler from an event.

        Args:
            event_name: The name of the event.
            handler: The handler to remove.
        """
        handlers = self._subscribers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)
            handler_name = getattr(handler, "__name__", repr(handler))
            logger.debug(f"Unsubscribed handler '{handler_name}' from event '{event_name}'")

    def publish(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Publish an event, invoking all subscribed handlers in order.

        Handler exceptions are caught and logged so a single failing
        subscriber cannot interrupt delivery to the others.

        Args:
            event_name: The name of the event to publish.
            *args: Positional arguments passed to each handler.
            **kwargs: Keyword arguments passed to each handler.
        """
        handlers = self._subscribers.get(event_name, [])
        if not handlers:
            logger.debug(f"No subscribers for event '{event_name}'")
            return

        for handler in handlers:
            handler_name = getattr(handler, "__name__", repr(handler))
            try:
                handler(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - isolate subscriber failures
                logger.error(
                    f"Error in handler '{handler_name}' for event '{event_name}': {exc}"
                )

    @property
    def event_names(self) -> list[str]:
        """Return the names of all events with at least one subscriber.

        Returns:
            A list of event names currently registered.
        """
        return list(self._subscribers.keys())
