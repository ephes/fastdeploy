import { SnakeToCamel } from "./typings";

/**
 * This module is used to convert different data representations.
 * Snake to camel case, utc to local time, etc.
 */

/**
 * This function converts snake case to camel case strings.
 *
 * @param str {string} The string to convert
 * @returns str {string} The converted string
 */
function snakeToCamelStr(str: string): string {
  if (!/[_-]/.test(str)) {
    return str;
  }
  return str
    .toLowerCase()
    .replace(/[-_][a-z0-9]/g, (group) => group.slice(-1).toUpperCase());
}

/**
 * This function uses the snakeToCamelStr function to convert all keys
 * of an object to camel case.
 *
 * @param obj {object} The object to convert
 * @returns newObj {object} The converted object
 */
export function snakeToCamel(obj: SnakeToCamel) {
  const newObj: any = {};
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      const newKey = snakeToCamelStr(key);
      newObj[newKey] = obj[key];
    }
  }
  return newObj;
}

/**
 * This function converts a utc date to a local date.
 *
 * @param date {Date} The date to convert
 * @returns newDate {Date} The converted date
 */
export function toUtcDate(date: Date): Date {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000);
}
