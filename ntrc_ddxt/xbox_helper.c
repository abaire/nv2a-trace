#include "xbox_helper.h"

#include "register_defs.h"

DWORD ReadDWORD(intptr_t address) { return *(DWORD*)(address); }

void WriteDWORD(intptr_t address, DWORD value) { *(DWORD*)(address) = value; }

void DisablePGRAPHFIFO(void) {
  DWORD state = ReadDWORD(PGRAPH_STATE);
  WriteDWORD(PGRAPH_STATE, state & 0xFFFFFFFE);
}

void EnablePGRAPHFIFO(void) {
  DWORD state = ReadDWORD(PGRAPH_STATE);
  WriteDWORD(PGRAPH_STATE, state | 0x00000001);
}

void BusyWaitUntilPGRAPHIdle(void) {
  while (ReadDWORD(PGRAPH_STATUS) & 0x00000001) {
  }
}

void PauseFIFOPuller(void) {
  DWORD state = ReadDWORD(CACHE_PULL_STATE);
  WriteDWORD(CACHE_PULL_STATE, state & 0xFFFFFFFE);
}

void ResumeFIFOPuller(void) {
  DWORD state = ReadDWORD(CACHE_PULL_STATE);
  WriteDWORD(CACHE_PULL_STATE, state | 0x00000001);
}

void PauseFIFOPusher(void) {
  DWORD state = ReadDWORD(CACHE_PUSH_STATE);
  WriteDWORD(CACHE_PUSH_STATE, state & 0xFFFFFFFE);
}

void ResumeFIFOPusher(void) {
  DWORD state = ReadDWORD(CACHE_PUSH_STATE);
  WriteDWORD(CACHE_PUSH_STATE, state | 0x00000001);
}

void BusyWaitUntilPusherIDLE(void) {
  const DWORD busy_bit = 1 << 4;
  while (ReadDWORD(CACHE_PUSH_STATE) & busy_bit) {
  }
}

void MaybePopulateFIFOCache(void) {
  ResumeFIFOPusher();
  PauseFIFOPuller();
}
