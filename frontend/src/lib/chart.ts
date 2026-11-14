/** Smooth curve through points that never overshoots (monotone cubic, Fritsch–Carlson).
 *  Keeps the line from dipping below/above the real values between data points. */
export function monotonePath(pts: [number, number][]): string {
  const n = pts.length
  if (n === 0) return ''
  if (n === 1) return `M${pts[0][0]},${pts[0][1]}`
  const dx: number[] = []
  const m: number[] = []
  // Width and slope of each segment between neighbouring points.
  for (let i = 0; i < n - 1; i++) {
    dx.push(pts[i + 1][0] - pts[i][0])
    m.push((pts[i + 1][1] - pts[i][1]) / dx[i])
  }
  const t: number[] = [m[0]]
  // Tangent at each inner point: flat at a peak or valley, otherwise the mean of the two slopes.
  for (let i = 1; i < n - 1; i++) t.push(m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2)
  t.push(m[n - 2])
  // Fritsch–Carlson pass: shrink tangents that would make a segment overshoot.
  for (let i = 0; i < n - 1; i++) {
    // A flat segment must stay flat, so both its tangents go to zero.
    if (m[i] === 0) {
      t[i] = 0
      t[i + 1] = 0
      continue
    }
    const a = t[i] / m[i]
    const b = t[i + 1] / m[i]
    const s = a * a + b * b
    // Outside the radius-3 circle the cubic can overshoot, so scale the tangents back onto it.
    if (s > 9) {
      const tau = 3 / Math.sqrt(s)
      t[i] = tau * a * m[i]
      t[i + 1] = tau * b * m[i]
    }
  }
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`
  // One cubic Bezier per segment, with control points a third of the way along each tangent.
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3
    d +=
      ` C${(pts[i][0] + h).toFixed(1)},${(pts[i][1] + t[i] * h).toFixed(1)}` +
      ` ${(pts[i + 1][0] - h).toFixed(1)},${(pts[i + 1][1] - t[i + 1] * h).toFixed(1)}` +
      ` ${pts[i + 1][0].toFixed(1)},${pts[i + 1][1].toFixed(1)}`
  }
  return d
}
