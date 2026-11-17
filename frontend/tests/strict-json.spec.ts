import { MAX_JSON_DEPTH, readStrictJson } from '../src/strictJson';

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

it('admits nesting up to the stated depth and refuses deeper JSON with the same error', () => {
  const nest = (depth: number) => '['.repeat(depth - 1) + '{"k":1}' + ']'.repeat(depth - 1);
  expect(readStrictJson(nest(MAX_JSON_DEPTH))).toEqual(JSON.parse(nest(MAX_JSON_DEPTH)));
  expect(() => readStrictJson(nest(MAX_JSON_DEPTH + 1))).toThrow('Invalid server JSON.');
  expect(() => readStrictJson('['.repeat(50_000) + ']'.repeat(50_000))).toThrow('Invalid server JSON.');
});
