export function chartTick(value: unknown) {
  return typeof value === 'number' && value !== 0 && (Math.abs(value) >= 1e6 || Math.abs(value) < .001)
    ? value.toExponential(2).replace(/\.?0+e/, 'e').replace('e+', 'e')
    : String(value);
}
