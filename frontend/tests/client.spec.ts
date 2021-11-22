import { snakeToCamel } from "../src/client";

describe("Test snakeToCamel function", () => {
  it("converts snake to camel case", () => {
    const testCases = [
        [{ testCase: "foobar" }, { testCase: "foobar" }],
        [{ test_case: "foobar" }, { testCase: "foobar" }],
    ];
    testCases.forEach(([input, expected]) => {
      expect(snakeToCamel(input)).toStrictEqual(expected);
    });
  });
});
