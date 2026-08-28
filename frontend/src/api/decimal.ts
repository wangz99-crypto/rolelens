const DECIMAL_PATTERN = /^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/;

function shiftDecimalString(value: string, places: number): string {
  const match = DECIMAL_PATTERN.exec(value.trim());
  if (!match || (!match[2] && !match[3])) {
    throw new Error("Invalid decimal string.");
  }

  const sign = match[1] === "-" ? "-" : "";
  const whole = match[2] || "0";
  const fraction = match[3] || "";
  const exponent = match[4] ? parseInt(match[4], 10) : 0;
  const digits = `${whole}${fraction}`;
  const decimalIndex = whole.length + exponent + places;

  let shiftedWhole: string;
  let shiftedFraction: string;
  if (decimalIndex <= 0) {
    shiftedWhole = "0";
    shiftedFraction = `${"0".repeat(-decimalIndex)}${digits}`;
  } else if (decimalIndex >= digits.length) {
    shiftedWhole = `${digits}${"0".repeat(decimalIndex - digits.length)}`;
    shiftedFraction = "";
  } else {
    shiftedWhole = digits.slice(0, decimalIndex);
    shiftedFraction = digits.slice(decimalIndex);
  }

  const canonicalWhole = shiftedWhole.replace(/^0+(?=\d)/, "") || "0";
  const canonicalFraction = shiftedFraction.replace(/0+$/, "");
  const canonical = canonicalFraction
    ? `${canonicalWhole}.${canonicalFraction}`
    : canonicalWhole;
  return canonical === "0" ? "0" : `${sign}${canonical}`;
}

export function canonicalDecimalString(value: string | number): string {
  return shiftDecimalString(String(value), 0);
}

export function percentageStringToFractionString(value: string): string {
  return shiftDecimalString(value, -2);
}

export function fractionToPercentDisplay(value: string | number): string {
  const percentage = shiftDecimalString(String(value), 2);
  return percentage.includes(".") ? percentage : `${percentage}.0`;
}
