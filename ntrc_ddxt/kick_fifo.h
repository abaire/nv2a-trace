#ifndef NV2A_TRACE_KICK_FIFO_H
#define NV2A_TRACE_KICK_FIFO_H

#include <windows.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum KickResult {
  KICK_OK = 0x1337C0DE,
  KICK_TIMEOUT = 0x32555359,
  KICK_BAD_READ_PUSH_ADDR = 0x0BAD0000,
  KICK_PUSH_MODIFIED_IN_CALL = 0x00BADBAD,
} KickResult;

KickResult KickFIFO(DWORD expected_push);

#ifdef __cplusplus
};  // extern "C"
#endif

#endif  // NV2A_TRACE_KICK_FIFO_H
