#include "tracer_state_machine.h"

#include "xbdm.h"
#include "xbox_helper.h"

typedef struct TracerStateMachine {
  HANDLE processor_thread;
  DWORD processor_thread_id;

  CRITICAL_SECTION state_critical_section;
  TracerState state;

  BOOL dma_addresses_valid;
  DWORD dma_pull_addr;
  DWORD dma_push_addr;

  NotifyStateChangedHandler on_notify_state_changed;
} TracerStateMachine;

static TracerStateMachine state_machine = {0};

static __stdcall DWORD TracerThreadMain(LPVOID lpThreadParameter);
static void SetState(TracerState new_state);
static BOOL SetStateIfIdle(TracerState new_state);
static void Shutdown(void);
static void WaitForStablePushBufferState(void);

HRESULT TracerInitialize(NotifyStateChangedHandler on_notify_state_changed) {
  state_machine.on_notify_state_changed = on_notify_state_changed;
  state_machine.state = STATE_UNINITIALIZED;
  InitializeCriticalSection(&state_machine.state_critical_section);

  return XBOX_S_OK;
}

HRESULT TracerCreate(void) {
  // TODO: Verify that the state is something reasonable.

  state_machine.state = STATE_INIITIALIZING;

  state_machine.processor_thread = CreateThread(
      NULL, 0, TracerThreadMain, NULL, 0, &state_machine.processor_thread_id);
  if (!state_machine.processor_thread) {
    return XBOX_E_FAIL;
  }

  SetState(STATE_INITIALIZED);

  return XBOX_S_OK;
}

void TracerDestroy(void) {
  if (state_machine.state == STATE_UNINITIALIZED) {
    return;
  }

  TracerState state = TracerGetState();
  if (state == STATE_SHUTDOWN) {
    return;
  }

  SetState(STATE_SHUTDOWN_REQUESTED);
}

TracerState TracerGetState(void) {
  EnterCriticalSection(&state_machine.state_critical_section);
  TracerState ret = state_machine.state;
  LeaveCriticalSection(&state_machine.state_critical_section);
  return ret;
}

static void SetState(TracerState new_state) {
  EnterCriticalSection(&state_machine.state_critical_section);
  BOOL changed = state_machine.state != new_state;
  state_machine.state = new_state;
  LeaveCriticalSection(&state_machine.state_critical_section);

  if (changed && state_machine.on_notify_state_changed) {
    state_machine.on_notify_state_changed(new_state);
  }
}

static BOOL SetStateIfIdle(TracerState new_state) {
  BOOL ret = FALSE;
  EnterCriticalSection(&state_machine.state_critical_section);
  if (state_machine.state == STATE_IDLE) {
    state_machine.state = new_state;
    ret = TRUE;
  }
  LeaveCriticalSection(&state_machine.state_critical_section);

  if (ret && state_machine.on_notify_state_changed) {
    state_machine.on_notify_state_changed(new_state);
  }

  return ret;
}

HRESULT TracerBeginWaitForStablePushBufferState(void) {
  if (TracerGetState() == STATE_IDLE_STABLE_PUSH_BUFFER) {
    return XBOX_S_OK;
  }

  if (SetStateIfIdle(STATE_BEGIN_WAITING_FOR_STABLE_PUSH_BUFFER)) {
    return XBOX_S_OK;
  }
  return XBOX_E_ACCESS_DENIED;
}

static __stdcall DWORD TracerThreadMain(LPVOID lpThreadParameter) {
  while (1) {
    TracerState state = TracerGetState();
    if (state < STATE_INIITIALIZING) {
      break;
    }

    // TODO: IMPLEMENT ME.
    switch (state) {
      case STATE_BEGIN_WAITING_FOR_STABLE_PUSH_BUFFER:
        WaitForStablePushBufferState();
        break;

      default:
        break;
    }

    Sleep(10);
  }

  Shutdown();
  return 0;
}

static void Shutdown(void) {
  if (state_machine.dma_addresses_valid) {
    // Recover the real address
    SetDMAPushAddress(state_machine.dma_push_addr);
    state_machine.dma_addresses_valid = FALSE;
  }

  // We can continue the cache updates now.
  ResumeFIFOPusher();

  SetState(STATE_SHUTDOWN);
}

static void WaitForStablePushBufferState(void) {
  SetState(STATE_WAITING_FOR_STABLE_PUSH_BUFFER);

  DWORD dma_pull_addr = 0;
  DWORD dma_push_addr_real = 0;

  while (1) {
    if (TracerGetState() != STATE_WAITING_FOR_STABLE_PUSH_BUFFER) {
      break;
    }

    // Stop consuming CACHE entries.
    DisablePGRAPHFIFO();
    BusyWaitUntilPGRAPHIdle();

    // Kick the pusher so that it fills the CACHE.
    MaybePopulateFIFOCache();

    // Now drain the CACHE.
    EnablePGRAPHFIFO();

    // Check out where the PB currently is and where it was supposed to go.
    dma_push_addr_real = GetDMAPushAddress();
    dma_pull_addr = GetDMAPullAddress();

    // Check if we have any methods left to run and skip those.
    DMAState dma_state;
    GetDMAState(&dma_state);
    dma_pull_addr += dma_state.method_count * 4;

    // Hide all commands from the PB by setting PUT = GET.
    DWORD dma_push_addr_target = dma_pull_addr;
    SetDMAPushAddress(dma_push_addr_target);

    // Resume pusher - The PB can't run yet, as it has no commands to process.
    ResumeFIFOPusher();

    // We might get issues where the pusher missed our PUT (miscalculated).
    // This can happen as `dma_method_count` is not the most accurate.
    // Probably because the DMA is halfway through a transfer.
    // So we pause the pusher again to validate our state
    PauseFIFOPusher();

    // TODO: Determine whether a sleep is needed and optimize the value.
    Sleep(1000);

    DWORD dma_push_addr_check = GetDMAPushAddress();
    DWORD dma_pull_addr_check = GetDMAPullAddress();

    // We want the PB to be empty.
    if (dma_pull_addr_check != dma_push_addr_check) {
      DbgPrint("Pushbuffer not empty - PULL (0x%08X) != PUSH (0x%08X)\n",
               dma_pull_addr_check, dma_push_addr_check);
      continue;
    }

    // Ensure that we are at the correct offset
    if (dma_push_addr_check != dma_push_addr_target) {
      DbgPrint("Oops PUT was modified; got 0x%08X but expected 0x%08X!",
               dma_push_addr_check, dma_push_addr_target);
      continue;
    }

    SetState(STATE_IDLE_STABLE_PUSH_BUFFER);
    state_machine.dma_pull_addr = dma_pull_addr;
    state_machine.dma_push_addr = dma_push_addr_real;
    state_machine.dma_addresses_valid = TRUE;
    return;
  }

  DbgPrint("Wait for idle aborted, restoring PFIFO state...");
  SetDMAPushAddress(dma_push_addr_real);
  EnablePGRAPHFIFO();
  ResumeFIFOPusher();

  state_machine.dma_pull_addr = dma_pull_addr;
  state_machine.dma_push_addr = dma_push_addr_real;
  state_machine.dma_addresses_valid = TRUE;
}