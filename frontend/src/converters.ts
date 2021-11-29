import { SnakeToCamel } from "./typings";

function snakeToCamelStr(str: string): string {
  if (!/[_-]/.test(str)) {
    return str;
  }
  return str
    .toLowerCase()
    .replace(/[-_][a-z0-9]/g, (group) => group.slice(-1).toUpperCase());
}

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

export function toUtcDate(date: Date): Date {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000);
}
