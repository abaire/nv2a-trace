#ifndef NV2A_TRACE_EXCHANGE_U32_H
#define NV2A_TRACE_EXCHANGE_U32_H

#include <windows.h>

// Writes the given DWORD value to the given address, returning the previous
// value.
DWORD ExchangeDWORD(intptr_t address, DWORD value);

#endif  // NV2A_TRACE_EXCHANGE_U32_H
