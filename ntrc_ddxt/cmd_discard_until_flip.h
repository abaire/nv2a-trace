#ifndef NV2A_TRACE_NTRC_DDXT_CMD_DISCARD_UNTIL_FLIP_H_
#define NV2A_TRACE_NTRC_DDXT_CMD_DISCARD_UNTIL_FLIP_H_

#include "xbdm.h"

#define CMD_DISCARD_UNTIL_FLIP "discard_until_flip"

// Steps through pgraph commands, discarding them until the next frame flip,
// then returns to idle state.
HRESULT HandleDiscardUntilFlip(const char *command, char *response,
                               DWORD response_len, CommandContext *ctx);

#endif  // NV2A_TRACE_NTRC_DDXT_CMD_DISCARD_UNTIL_FLIP_H_
