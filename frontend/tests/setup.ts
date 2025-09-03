import { config } from '@vue/test-utils'

// Any global test setup can go here
// For example, global mocks or stubs

// Mock WebSocket if needed
global.WebSocket = class WebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  constructor(public url: string) {}
  send() {}
  close() {}
  addEventListener() {}
  removeEventListener() {}
} as any
