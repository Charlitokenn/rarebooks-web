// Decimal separators of Frappe's number formats, as its number_format_info holds them.
const NUMBER_FORMAT_DECIMALS: Record<string, string> = {
  '#,###.##': '.',
  '#.###,##': ',',
  '# ###.##': '.',
  '# ###,##': ',',
  "#'###.##": '.',
  '#, ###.##': '.',
  '#,##,###.##': '.',
  '#,###.###': '.',
  '#.###': '',
  '#,###': '',
  '#.########': '.',
};

/** Frappe's system defaults in the session boot, which Desk reads its number precisions from. */
function getSysDefaults() {
  return globalThis.window?.frappe?.boot?.sysdefaults ?? {};
}

/** Desk's precision of a Float field: the system float precision, or none. */
export function getFloatPrecision(): number | null {
  const precision = parseInt(getSysDefaults().float_precision ?? '');
  return Number.isNaN(precision) ? null : precision;
}

/** Desk's precision of a Currency field: the system currency precision, else that of the number format. */
export function getCurrencyPrecision(): number {
  const { currency_precision, number_format } = getSysDefaults();
  if (currency_precision) {
    return parseInt(currency_precision);
  }

  const format = number_format || '#,###.##';
  const decimal = NUMBER_FORMAT_DECIMALS[format] ?? '.';
  return decimal ? (format.split(decimal)[1]?.length ?? 0) : 0;
}

/** The rounding method Desk rounds typed numbers by. */
export function getRoundingMethod(): string {
  return getSysDefaults().rounding_method || "Banker's Rounding (legacy)";
}

/**
 * The number format Frappe's importer reads for the logged in user: their
 * Language record's, else System Settings', resolved on the server (spec 0025
 * AC-17). Not `sysdefaults.number_format`, which ignores the user's language.
 */
export function getImportNumberFormat(): string {
  return globalThis.window?.frappe?.boot?.books?.number_format || '#,###.##';
}

/**
 * A number as an import file writes it, by the number rule of spec 0025
 * AC-17: its digits, a leading `-` when negative, no thousands separator, no
 * exponent, trailing fractional zeros trimmed, and the format's own decimal
 * separator (`.` for a format with none). `value` is a number or plain
 * decimal text, such as a money value's stored text.
 */
export function getImportNumberText(
  value: number | string,
  numberFormat: string
): string {
  const text = getPlainDecimal(value);
  const decimal = NUMBER_FORMAT_DECIMALS[numberFormat] || '.';
  return text.replace('.', decimal);
}

function getPlainDecimal(value: number | string): string {
  let text =
    typeof value === 'number'
      ? value.toLocaleString('en-US', {
          useGrouping: false,
          maximumFractionDigits: 20,
        })
      : value.trim();
  text = text.replace(/^\+/, '');
  if (text.includes('.')) {
    text = text.replace(/0+$/, '').replace(/\.$/, '');
  }

  return /^-?0*$/.test(text) ? '0' : text;
}
