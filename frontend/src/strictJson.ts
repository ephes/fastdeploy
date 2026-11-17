import { visit } from 'jsonc-parser';

/** Deepest object/array nesting admitted from the server; the visitor recurses per level. */
export const MAX_JSON_DEPTH = 512;

/** Reject duplicate decoded member names before JSON.parse can discard them. */
export function readStrictJson(text: string): unknown {
  const objects: Set<string>[] = [];
  let depth = 0;
  const invalid = () => { throw new SyntaxError('Invalid server JSON.'); };
  const enter = () => { if (++depth > MAX_JSON_DEPTH) invalid(); };
  try {
    visit(text, {
      onObjectBegin: () => { enter(); objects.push(new Set()); },
      onObjectProperty: name => {
        const members = objects[objects.length - 1];
        if (members.has(name)) invalid();
        members.add(name);
      },
      onObjectEnd: () => { objects.pop(); depth--; },
      onArrayBegin: enter,
      onArrayEnd: () => { depth--; },
      onError: invalid,
    }, { disallowComments: true, allowTrailingComma: false, allowEmptyContent: false });
  } catch {
    // Keep diagnostics content-free and uniform, including engine stack errors.
    invalid();
  }
  // Keep standard JSON value/prototype semantics; the visitor only admits syntax,
  // nesting depth and member uniqueness, while the wire validators admit domain data.
  return JSON.parse(text);
}
