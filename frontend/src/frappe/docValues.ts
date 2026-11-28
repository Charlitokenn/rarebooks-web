import { Fyo } from 'fyo';
import { DocValue } from 'fyo/core/types';
import { isPesa } from 'fyo/utils';
import { isEqual } from 'lodash';
import { DateTime } from 'luxon';
import { Field, FieldType, FieldTypeEnum } from 'schemas/types';
import { getIsNullOrUndef } from 'utils';
import type { FrappeDoc } from './document';

/** Whether two values of a field are equal: amounts by value, dates by time. */
export function areDocValuesEqual(
  dvOne: DocValue | FrappeDoc[],
  dvTwo: DocValue | FrappeDoc[]
): boolean {
  if (dvOne instanceof Date) {
    return dvTwo instanceof Date && dvOne.getTime() === dvTwo.getTime();
  }

  if (['string', 'number'].includes(typeof dvOne)) {
    return dvOne === dvTwo;
  }

  if (isPesa(dvOne)) {
    return !getIsNullOrUndef(dvTwo) && dvOne.eq(dvTwo as string | number);
  }

  return isEqual(dvOne, dvTwo);
}

/** A field's default, with Frappe's "Now" and "Today" taken when the document is made. */
export function getFieldDefault(field: Field): DocValue | undefined {
  const isNow = field.default === 'Now' || field.default === 'Today';
  if (isNow && field.fieldtype === FieldTypeEnum.Date) {
    return getSystemToday();
  }

  if (isNow && field.fieldtype === FieldTypeEnum.Datetime) {
    return new Date();
  }

  return field.default as DocValue | undefined;
}

/**
 * Today in the site's time zone, as the browser's midnight of that day.
 * A Date field saves the browser's calendar day, and the server dates the ledger and the
 * dashboard's "as of" in the site's zone. Saving the browser's own today would put a document
 * opened ahead of the site (Tanzania on a US site) on the site's tomorrow, outside today's balances.
 */
function getSystemToday(): Date {
  const zone = window.frappe?.boot?.time_zone?.system;
  const today = zone ? DateTime.now().setZone(zone) : DateTime.now();
  return new Date(today.year, today.month - 1, today.day);
}

/** The value a field of the type starts with when it has no default. */
export function getPreDefaultValues(
  fieldtype: FieldType,
  fyo: Fyo
): DocValue | FrappeDoc[] {
  switch (fieldtype) {
    case FieldTypeEnum.Table:
      return [] as FrappeDoc[];
    case FieldTypeEnum.Currency:
      return fyo.pesa(0.0);
    case FieldTypeEnum.Int:
    case FieldTypeEnum.Float:
      return 0;
    // A check box is never empty; a custom one has no schema default.
    case FieldTypeEnum.Check:
      return false;
    default:
      return null;
  }
}

/** Whether a value is set: a nonzero amount, a table with rows. */
export function isDocValueTruthy(docValue: DocValue | FrappeDoc[]) {
  if (isPesa(docValue)) {
    return !docValue.isZero();
  }

  if (Array.isArray(docValue)) {
    return docValue.length > 0;
  }

  return !!docValue;
}

/** Numbers the rows by their place in the table. */
export function setChildDocIdx(childDocs: FrappeDoc[]) {
  childDocs.forEach((cd, idx) => {
    cd.idx = idx;
  });
}
