import { HasStringKeys } from "./typings";

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
export function snakeToCamel(obj: HasStringKeys) {
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
 * This function converts a utc string to a local date.
 *
 * The utc strings from backend are using microsecond precision,
 * but javascript uses millisecond precision. This is converted
 * automatically when creating the date object from a string.
 *
 * @param utcString {string} The utc string to convert
 * @returns newDate {Date} The converted date
 */
export function utcStringToLocalDate(utcString: string | null): Date | null {
  if (!utcString) {
    return null;
  } else {
    // dunno why I don't have to append Z anymore :( weird
    // return new Date(`${utcString}Z`);
    return new Date(utcString);
  }
}

/**
 * This function converts an object with utc date strings
 * to an object with local date objects. Taking the object
 * and a list of keys to convert as parameters.
 *
 * @param obj {object} The object to convert
 * @returns newObj {object} The converted object
 */
export function utcStringObjToLocalDateObj(
  obj: HasStringKeys,
  keys: string[] = ["created", "started", "finished"]
): HasStringKeys {
  const newObj: HasStringKeys = { ...obj };
  for (const key of keys) {
    if (obj.hasOwnProperty(key)) {
      newObj[key] = utcStringToLocalDate(obj[key]);
    }
  }
  return newObj;
}

/**
 * Convert an object from server and convert it to a local object
 * where all keys are camel case and all date values are converted to
 * local utc dates.
 *
 * @param obj {object} The object to convert
 * @returns newObj {object} The converted object
 */
 export function pythonToJavascript(obj: HasStringKeys): HasStringKeys {
  return utcStringObjToLocalDateObj(snakeToCamel(obj));
 }
