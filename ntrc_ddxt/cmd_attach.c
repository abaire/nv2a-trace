#include "cmd_attach.h"

#include <stdio.h>

#include "tracer_state_machine.h"

HRESULT HandleAttach(const char *command, char *response, DWORD response_len,
                     CommandContext *ctx) {
  HRESULT ret = TracerCreate();
  sprintf(response, "TracerCreate");
  return ret;
}
