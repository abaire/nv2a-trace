#ifndef NV2A_TRACE_CMD_HELLO_H
#define NV2A_TRACE_CMD_HELLO_H

#include "xbdm.h"

// Enumerates the command table.
HRESULT HandleHello(const char *command, char *response, DWORD response_len,
                    CommandContext *ctx);

#endif  // NV2A_TRACE_CMD_HELLO_H
