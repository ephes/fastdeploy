// Any global test setup can go here
// For example, global mocks or stubs

class MemoryStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value)
  }
}

for (const key of ['localStorage', 'sessionStorage'] as const) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    enumerable: true,
    writable: true,
    value: new MemoryStorage(),
  })
}

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
