/** Tab messaging is optional in restricted browsers and embedded contexts. */
export function openBroadcastChannel(name: string): BroadcastChannel | null {
  try {
    return typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(name);
  } catch {
    return null;
  }
}
