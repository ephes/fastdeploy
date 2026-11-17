import { readStrictJson } from '../src/strictJson';

it.each([
  '', '{"key":1,}', '[1,]', '{/* comment */"key":1}', 'true false', '{"key":}',
  '{"key":1,"key":1}', '{"items":[{"key":1,"k\\u0065y":2}]}',
  '{"__proto__":{},"__proto__":{}}', '{"constructor":1,"constructor":2}',
])('rejects nonstandard or ambiguous JSON with a content-free error: %s', raw => {
  expect(() => readStrictJson(raw)).toThrow('Invalid server JSON.');
});

it.each([
  'null', 'false', '123', '"text"', '[]', '{}',
  '{"items":[{"key":1},{"key":2}],"nested":{"items":[]}}',
  '{"__proto__":{"synthetic":true},"constructor":2,"toString":3}',
  '{"text":"escaped \\"key\\": and braces {} []","unicode":"ä"}',
])('keeps ordinary JSON semantics and independent object scopes: %s', raw => {
  expect(readStrictJson(raw)).toEqual(JSON.parse(raw));
});
