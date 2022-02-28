#ifndef NV2A_TRACE_TRACER_STATE_MACHINE_H
#define NV2A_TRACE_TRACER_STATE_MACHINE_H

#include <windows.h>

typedef enum TracerState {
  STATE_SHUTDOWN_REQUESTED = -2,
  STATE_SHUTDOWN = -1,

  STATE_UNINITIALIZED = 0,

  STATE_INIITIALIZING = 1,
  STATE_INITIALIZED,

  STATE_IDLE = 100,
  STATE_IDLE_STABLE_PUSH_BUFFER,
  STATE_IDLE_LAST,  // Last entry in the block of "idle" states.

  STATE_BEGIN_WAITING_FOR_STABLE_PUSH_BUFFER = 1000,
  STATE_WAITING_FOR_STABLE_PUSH_BUFFER,

} TracerState;

// Callback to be invoked when the tracer state changes.
typedef void (*NotifyStateChangedHandler)(TracerState);

HRESULT TracerInitialize(NotifyStateChangedHandler on_notify_state_changed);

HRESULT TracerCreate(void);
void TracerDestroy(void);

TracerState TracerGetState(void);

HRESULT TracerBeginWaitForStablePushBufferState(void);

#endif  // NV2A_TRACE_TRACER_STATE_MACHINE_H
