import { config } from '@vue/test-utils'

// Any global test setup can go here
// For example, global mocks or stubs

// Mock WebSocket if needed
global.WebSocket = class WebSocket {
  constructor(public url: string) {}
  send() {}
  close() {}
  addEventListener() {}
  removeEventListener() {}
}
