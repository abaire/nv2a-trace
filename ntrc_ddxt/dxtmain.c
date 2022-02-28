#include "dxtmain.h"

#include <stdio.h>
#include <string.h>

#include "cmd_get_state.h"
#include "cmd_hello.h"
#include "cmd_wait_for_stable_push_buffer_state.h"

// Command prefix that will be handled by this processor.
// Keep in sync with value in ntrc.py
static const char kHandlerName[] = "ntrc";
static const uint32_t kTag = 0x6E747263;  // 'ntrc'

static const CommandTableEntry kCommandTableDef[] = {
    {CMD_GET_STATE, HandleGetState},
    {CMD_HELLO, HandleHello},
    {CMD_WAIT_FOR_STABLE_PUSH_BUFFER, HandleWaitForStablePushBufferState},
};
const CommandTableEntry *kCommandTable = kCommandTableDef;
const uint32_t kCommandTableNumEntries =
    sizeof(kCommandTableDef) / sizeof(kCommandTableDef[0]);

static HRESULT_API ProcessCommand(const char *command, char *response,
                                  DWORD response_len,
                                  struct CommandContext *ctx);

HRESULT __declspec(dllexport) DxtMain(void) {
  return DmRegisterCommandProcessor(kHandlerName, ProcessCommand);
}

static HRESULT_API ProcessCommand(const char *command, char *response,
                                  DWORD response_len,
                                  struct CommandContext *ctx) {
  const char *subcommand = command + sizeof(kHandlerName);

  const CommandTableEntry *entry = kCommandTable;
  for (uint32_t i = 0; i < kCommandTableNumEntries; ++i, ++entry) {
    uint32_t len = strlen(entry->command);
    if (!strncmp(subcommand, entry->command, len)) {
      return entry->processor(subcommand + len, response, response_len, ctx);
    }
  }

  return XBOX_E_UNKNOWN_COMMAND;
}
