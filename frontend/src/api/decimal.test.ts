import { describe, expect, it } from "vitest";
import {
  fractionToPercentDisplay,
  percentageStringToFractionString,
} from "./decimal";

describe("exact decimal transport and display", () => {
  it.each([
    ["3", "0.03"],
    ["7.0", "0.07"],
    ["33.3", "0.333"],
    ["0.1", "0.001"],
    ["100", "1"],
  ])("shifts percentage %s to the exact fraction %s", (percentage, fraction) => {
    expect(percentageStringToFractionString(percentage)).toBe(fraction);
  });

  it.each([
    [0.08, "8.0"],
    [0.07, "7.0"],
    [0.333, "33.3"],
    [0.001, "0.1"],
    [1, "100.0"],
  ])("formats fraction %s as editable percentage %s", (fraction, percentage) => {
    expect(fractionToPercentDisplay(fraction)).toBe(percentage);
  });
});
