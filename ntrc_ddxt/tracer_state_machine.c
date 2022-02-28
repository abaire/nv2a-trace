#include "tracer_state_machine.h"

#include "xbdm.h"

typedef struct TracerStateMachine {
  HANDLE processor_thread;
  DWORD processor_thread_id;

  CRITICAL_SECTION state_critical_section;
  TracerState state;
} TracerStateMachine;

static TracerStateMachine state_machine = {0};

static __stdcall DWORD TracerThreadMain(LPVOID lpThreadParameter);

HRESULT Initialize(void) {
  // TODO: Verify that the state is something reasonable.

  state_machine.state = STATE_INIITIALIZING;

  InitializeCriticalSection(&state_machine.state_critical_section);
  state_machine.processor_thread =
      CreateThread(NULL, 0, TracerThreadMain, (void *)&state_machine, 0,
                   &state_machine.processor_thread_id);
  if (!state_machine.processor_thread) {
    return XBOX_E_FAIL;
  }

  state_machine.state = STATE_INIITALIZED;

  return XBOX_S_OK;
}

TracerState GetTracerState(void) {
  EnterCriticalSection(&state_machine.state_critical_section);
  TracerState ret = state_machine.state;
  LeaveCriticalSection(&state_machine.state_critical_section);
  return ret;
}

HRESULT BeginWaitForStablePushBufferState(void) {
  HRESULT ret;
  EnterCriticalSection(&state_machine.state_critical_section);
  if (state_machine.state == STATE_IDLE) {
    state_machine.state = STATE_BEGIN_WAITING_FOR_STABLE_PUSH_BUFFER;
    ret = XBOX_S_OK;
  } else {
    ret = XBOX_E_ACCESS_DENIED;
  }
  LeaveCriticalSection(&state_machine.state_critical_section);
  return ret;
}

static __stdcall DWORD TracerThreadMain(LPVOID lpThreadParameter) {
  while (1) {
    TracerState state = GetTracerState();
    if (state < STATE_INIITIALIZING) {
      break;
    }

    // TODO: IMPLEMENT ME.
    switch (state) {
      default:
        break;
    }

    Sleep(100);
  }

  EnterCriticalSection(&state_machine.state_critical_section);
  state_machine.state = STATE_SHUTDOWN;
  LeaveCriticalSection(&state_machine.state_critical_section);

  return 0;
}
