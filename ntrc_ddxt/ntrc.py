"""Python interface to the ntrc Dynamic DXT module."""

import enum
import re
import threading
from typing import Tuple

from . import xbdm_notification_processor
from xboxpy.interface import if_xbdm

# Seconds to wait between ntrc tracer state polls.
_AWAIT_STATE_BUSY_LOOP_SLEEP_TIME = 0.001

_HEX_VALUE = r"0x[0-9a-fA-F]+"
_CAP_HEX_VALUE = r"(" + _HEX_VALUE + r")"

_STATE_RE = re.compile(r"\s*state=" + _CAP_HEX_VALUE)
_DMA_ADDRS_RE = re.compile(r"\s*push=" + _CAP_HEX_VALUE + " pull=" + _CAP_HEX_VALUE)

_NOTIF_NEW_STATE_RE = re.compile(r"new_state=" + _CAP_HEX_VALUE)


class ShutdownException(Exception):
    """Exception raised when the remote tracer enters a shutdown state."""

    def __init__(self, state):
        super().__init__(f"Shutdown: {state}")


@enum.unique
class TracerState(enum.IntEnum):
    """Tracer state machine states exposed by the ntrc DLL."""

    # Keep in sync with tracer_state_machine.h
    STATE_SHUTDOWN_REQUESTED = -2
    STATE_SHUTDOWN = -1

    STATE_UNINITIALIZED = 0

    STATE_INITIALIZING = 1
    STATE_INITIALIZED = 2

    STATE_IDLE = 100
    STATE_IDLE_STABLE_PUSH_BUFFER = 101

    STATE_BEGIN_WAITING_FOR_STABLE_PUSH_BUFFER = 1000
    STATE_WAITING_FOR_STABLE_PUSH_BUFFER = 1001

    STATE_UNKNOWN = 0xFFFFFFFF


class NTRC:
    """Python interface to the ntrc Dynamic DXT module."""

    # Keep in sync with value in dxtmain.c
    _COMMAND_PREFIX = "ntrc!"

    def __init__(self):
        self._connected = False
        self._tracer_state = TracerState.STATE_UNKNOWN
        self._tracer_state_cv = threading.Condition()

    def connect(self) -> bool:
        """Verifies that the ntrc handler is available."""
        if self._connected:
            return True

        status, message = self._send("hello")
        if status != 202:
            print(f"Failed to communicate with ntrc module: {status} {message}")
            return False

        self._connected = True
        self._notification_server = (
            xbdm_notification_processor.create_notification_server()
        )
        self._notification_server.add_message_handler("ntrc", self._handle_notification)
        xbdm_notification_processor.start_notification_server(self._notification_server)
        return True

    def startup(self):
        status, message = self._send("attach")
        if status != 200:
            raise Exception(f"Failed to startup ntrc module {status} {message}")

    def shutdown(self):
        """Gracefully deactivates the ntrc module."""
        if not self._connected:
            return

        status, message = self._send("detach")
        if status != 200:
            print(
                f"Failed to request shutdown from ntrc module, xbox state may be invalid."
            )

        max_wait_secs = 10
        print(f"Waiting up to {max_wait_secs} seconds for ntrc shutdown")
        self._await_states([TracerState.STATE_SHUTDOWN], max_wait_secs)

        xbdm_notification_processor.stop_notification_server(self._notification_server)

    def wait_for_idle_state(self, max_seconds=None):
        """Wait until the tracer returns to an idle state."""
        self._await_states(
            [TracerState.STATE_IDLE, TracerState.STATE_IDLE_STABLE_PUSH_BUFFER],
            max_seconds,
        )

    def wait_for_stable_push_buffer_state(self):
        """Ask the xbox to busyloop until the pushbuffer is in a state ready for tracing.

        Returns: dma_push_addr, dma_pull_addr
        """
        status, message = self._send("wait_stable_pb")
        if status != 200:
            raise Exception(f"Failed to begin wait: {status} {message}")

        self._await_states([TracerState.STATE_IDLE_STABLE_PUSH_BUFFER])

        push_addr, pull_addr = self._get_dma_addresses()
        if push_addr is None or pull_addr is None:
            raise Exception("Failed to retrieve DMA addresses")

        return push_addr, pull_addr

    def _handle_notification(self, message, sender_addr):
        message = message[5:]
        match = _NOTIF_NEW_STATE_RE.match(message)
        if match:
            self._update_state(int(match.group(1), 16))
            return

        print(f"NTRC: Unknown: {sender_addr} {message}")

    def _update_state(self, new_state):
        with self._tracer_state_cv:
            self._tracer_state = new_state
            self._tracer_state_cv.notify()

    def _get_dma_addresses(self):
        status, message = self._send("dma_addrs")
        if status != 200:
            raise Exception(f"Failed to retrieve DMA addresses: {status} {message}")

        if "invalid" in message:
            return None, None

        match = _DMA_ADDRS_RE.match(message)
        if not match:
            raise Exception(
                f"Invalid response to dma_addrs request: {status} {message}"
            )

        push_addr, pull_addr = match.group(1), match.group(2)
        return int(push_addr, 16), int(pull_addr, 16)

    def _send(self, command_string) -> Tuple[int, str]:
        return if_xbdm.xbdm_command(self._COMMAND_PREFIX + command_string)

    def _await_states(self, target_states, max_seconds=None):
        def check_state():
            current_state = self._tracer_state
            if (
                current_state in target_states
                or current_state < TracerState.STATE_INITIALIZING
            ):
                return (True, current_state)
            return False

        with self._tracer_state_cv:
            state = self._tracer_state_cv.wait_for(check_state, max_seconds)

        if not state:
            return False

        state = state[1]
        print(f"_await_states: New state: {state}")
        if state < TracerState.STATE_INITIALIZING:
            raise ShutdownException(state)

        return True
