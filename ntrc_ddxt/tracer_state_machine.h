#ifndef NV2A_TRACE_TRACER_STATE_MACHINE_H
#define NV2A_TRACE_TRACER_STATE_MACHINE_H

#include <windows.h>

// Note: Entries with explicit values are intended for consumption by Python.
typedef enum TracerState {
  STATE_FATAL_ERROR_DISCARDING_FAILED = -1010,
  STATE_FATAL_ERROR_PROCESS_PUSH_BUFFER_COMMAND_FAILED = -1000,

  STATE_SHUTDOWN_REQUESTED = -2,
  STATE_SHUTDOWN = -1,

  STATE_UNINITIALIZED = 0,

  STATE_INIITIALIZING = 1,
  STATE_INITIALIZED = 2,

  STATE_IDLE = 100,
  STATE_IDLE_STABLE_PUSH_BUFFER = 101,
  STATE_IDLE_NEW_FRAME = 102,
  STATE_IDLE_LAST,  // Last entry in the block of "idle" states.

  STATE_WAITING_FOR_STABLE_PUSH_BUFFER = 1000,

  STATE_DISCARDING_UNTIL_FLIP = 1010,
} TracerState;

// Callback to be invoked when the tracer state changes.
typedef void (*NotifyStateChangedHandler)(TracerState);

HRESULT TracerInitialize(NotifyStateChangedHandler on_notify_state_changed);

HRESULT TracerCreate(void);
void TracerDestroy(void);

TracerState TracerGetState(void);
BOOL TracerGetDMAAddresses(DWORD *push_addr, DWORD *pull_addr);

HRESULT TracerBeginWaitForStablePushBufferState(void);
HRESULT TracerBeginDiscardUntilFlip(void);

#endif  // NV2A_TRACE_TRACER_STATE_MACHINE_H
