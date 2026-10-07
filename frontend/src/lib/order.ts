/** Indexes of items out of their original order: everything outside the longest run that is
 * still in order (equal values count as in order). Moving one line marks that line only,
 * not every line after it. Mirrors backend `tailoring.diff.moved`. */
export function movedIndexes(order: number[]): Set<number> {
  const tails: number[] = [];
  const tailIndex: number[] = [];
  const parent: number[] = new Array(order.length).fill(-1);
  order.forEach((value, i) => {
    let low = 0;
    let high = tails.length;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (tails[mid]! <= value) low = mid + 1;
      else high = mid;
    }
    tails[low] = value;
    tailIndex[low] = i;
    parent[i] = low > 0 ? tailIndex[low - 1]! : -1;
  });
  const keep = new Set<number>();
  for (let i = tailIndex[tails.length - 1] ?? -1; i !== -1; i = parent[i]!) keep.add(i);
  return new Set(order.map((_, i) => i).filter((i) => !keep.has(i)));
}
