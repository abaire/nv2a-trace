"""Registers for and processes XBDM notifications."""

import collections
import logging
import re
import select
import socket
import threading

from xboxpy.interface import if_xbdm

logger = logging.getLogger(__name__)


class XBDMNotificationListener:
    """Listens for and processes XBDM notification events."""

    _SELECT_TIMEOUT_SECS = 0.25

    # Match up to the first whitespace or "!" character.
    _PREFIX_RE = re.compile(r"^(\w+?)[!\s]")

    class Client:
        """Models a connection from an XBDM notification process."""

        _TERMINATOR = b"\r\n"

        def __init__(self, sock, addr, process_message):
            self.sock = sock
            self.addr = addr
            self._read_buffer = bytearray()
            self._process_message = process_message

        def receive(self) -> bool:
            """Reads data from the socket and optionally processes it.

            :return bool indicating whether the socket should be closed.
            """
            self._read_buffer.extend(self.sock.recv(4096))
            terminator = self._read_buffer.find(self._TERMINATOR)
            while terminator >= 0:
                message = self._read_buffer[:terminator].decode("utf-8")
                self._read_buffer = bytearray(
                    self._read_buffer[terminator + len(self._TERMINATOR) :]
                )
                terminator = self._read_buffer.find(self._TERMINATOR)
                self._process_message(self, message)
            return True

        def __str__(self):
            return f"{self.__class__.__name__}@{self.addr}"

    def __init__(self, addr=None):
        self._sock = socket.create_server(addr, backlog=1)
        self._addr = self._sock.getsockname()
        self._stop_event = threading.Event()
        self._thread = None
        self._connections = set()
        self._message_handlers = collections.defaultdict(list)

    def start(self):
        """Starts accepting connections."""
        if self._thread:
            raise Exception("Attempt to start a running instance")

        self._stop_event.clear()
        self._connections.clear()
        self._thread = threading.Thread(target=self._thread_main)
        self._thread.daemon = True
        self._thread.start()

    def shutdown(self):
        """Stops the server and destroys the thread."""
        self._stop_event.set()
        self._thread.join()
        self._thread = None

    def add_message_handler(self, prefix, handler):
        """Adds a method to be called when a notification starting with the given prefix is received."""
        self._message_handlers[prefix].append(handler)

    @property
    def listen_ip(self):
        """Returns the IP address of the server socket."""
        return self._addr[0]

    @property
    def listen_port(self):
        """Returns the port of the server socket."""
        return self._addr[1]

    def _thread_main(self, *args):
        del args

        while not self._stop_event.is_set():
            readable = [self._sock]
            writable = []
            exceptional = [self._sock]

            for conn in self._connections:
                readable.append(conn.sock)
                exceptional.append(conn.sock)

            readable, writable, exceptional = select.select(
                readable, writable, exceptional, self._SELECT_TIMEOUT_SECS
            )

            if self._sock in exceptional:
                logger.error(f"Socket exception in {self}")
                break

            if self._sock in readable:
                self._accept()

            dead_connections = set()
            for conn in self._connections:
                if conn.sock in exceptional:
                    dead_connections.add(conn)
                    continue
                if conn.sock in readable:
                    if not conn.receive():
                        dead_connections.add(conn)
            self._connections -= dead_connections

    def _accept(self):
        try:
            remote, remote_addr = self._sock.accept()
        except OSError:
            logger.error(f"Socket accept failed in {self}")
            return False

        self._connections.add(
            self.__class__.Client(remote, remote_addr, self._on_notification_received)
        )
        return True

    def _on_notification_received(self, client, message):
        match = self._PREFIX_RE.match(message)
        if not match:
            logger.warning(
                f"Received notification without prefix: {client.addr[0]}:{client.addr[1]}: {message}"
            )
            return

        prefix = match.group(1)
        if prefix not in self._message_handlers:
            logger.debug(
                f"Received notification with unknown prefix: {client.addr[0]}:{client.addr[1]}: {message}"
            )
            return

        for handler in self._message_handlers[prefix]:
            handler(message, client.addr)

    def __str__(self):
        if getattr(self, "_addr"):
            return f"{self.__class__.__name__}@{self._addr}"
        return {self.__class__.__name__}


_DEBUGSTR_RE = re.compile(r"debugstr\s+thread=(\d+)(?:\s+(lf|cr|crlf))?\s+string=(.*)")


def _handle_debugstr(message, sender_addr):
    match = _DEBUGSTR_RE.match(message)
    if not match:
        logger.warning(f"Received unparsable debugstr '{message}' from {sender_addr}")
        return

    thread_id = match.group(1)
    data = match.group(3)

    termination_type = match.group(2)
    if termination_type == "lf":
        data += "\n"
    elif termination_type == "cr":
        data += "\r"
    elif termination_type == "crlr":
        data += "\r\n"

    print(f"DBGMSG: {sender_addr}#{thread_id} {data}", end="")


def create_notification_server(addr=None) -> XBDMNotificationListener:
    """Creates a new notification listener and registers it with XBDM."""
    if not addr:
        addr = "", 0

    server = XBDMNotificationListener(addr)
    server.add_message_handler("debugstr", _handle_debugstr)
    return server


def start_notification_server(server):
    server.start()
    status, message = if_xbdm.xbdm_command(
        f"notifyat port=0x{server.listen_port:x} debug"
    )
    if status != 200:
        logger.warning(f"Failed to initiate notification listener: {status} {message}")


def stop_notification_server(server: XBDMNotificationListener):
    """Unregisters the given server and shuts it down."""
    status, message = if_xbdm.xbdm_command(
        f"notifyat port=0x{server.listen_port:x} drop debug"
    )
    if status != 200:
        logger.warning(f"Failed to terminate notification listener: {status} {message}")
    server.shutdown()
