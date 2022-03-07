#ifndef NV2A_TRACE_NTRC_DDXT_CIRCULAR_BUFFER_IMPL_H_
#define NV2A_TRACE_NTRC_DDXT_CIRCULAR_BUFFER_IMPL_H_

typedef struct CircularBufferImpl {
  uint8_t *buffer;
  size_t size;

  size_t read;
  size_t write;

  CBFreeProc free_proc;
} CircularBufferImpl;

#endif  // NV2A_TRACE_NTRC_DDXT_CIRCULAR_BUFFER_IMPL_H_
