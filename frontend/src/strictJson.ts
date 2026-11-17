import { visit } from 'jsonc-parser';

/** Reject duplicate decoded member names before JSON.parse can discard them. */
export function readStrictJson(text: string): unknown {
  const objects: Set<string>[] = [];
  const invalid = () => { throw new SyntaxError('Invalid server JSON.'); };
  visit(text, {
    onObjectBegin: () => { objects.push(new Set()); },
    onObjectProperty: name => {
      const members = objects[objects.length - 1];
      if (members.has(name)) invalid();
      members.add(name);
    },
    onObjectEnd: () => { objects.pop(); },
    onError: invalid,
  }, { disallowComments: true, allowTrailingComma: false, allowEmptyContent: false });
  // Keep standard JSON value/prototype semantics; the visitor only admits syntax
  // and member uniqueness, while the existing wire validators admit domain data.
  return JSON.parse(text);
}
