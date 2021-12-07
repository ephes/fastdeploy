import { snakeToCamel } from "../src/converters";
import { utcStringToLocalDate } from "../src/converters";

describe("Test snakeToCamel function", () => {
  it("converts snake to camel case", () => {
    const testCases = [
      [{ testCase: "foobar" }, { testCase: "foobar" }],
      [{ test_case: "foobar" }, { testCase: "foobar" }],
      [{ test_23case: "foobar" }, { test23case: "foobar" }],
    ];
    testCases.forEach(([input, expected]) => {
      expect(snakeToCamel(input)).toStrictEqual(expected);
    });
  });
});

describe("Test utc string to local date", () => {
  it("converts utc string to local date", () => {
    const testCases = [
      // note that javascript month is zero-based
      // note that javascript date constructor takes milliseconds, python generates microseconds
      ["2021-12-07T09:14:26.636703", new Date(2021, 11, 7, 10, 14, 26, 636)],
    ];
    testCases.forEach(([input, expected]) => {
      if (typeof input === "string") {
        const actual = utcStringToLocalDate(input);
        expect(utcStringToLocalDate(input)).toEqual(expected);
      }
    });
  });
});
