import { useState, type SetStateAction } from 'react';

/** Navigation state changes together so rapid jumps always animate in order. */
export function useQuestionNavigation(initial: number | (() => number) = 0) {
  const [navigation, setNavigation] = useState(() => ({
    index: typeof initial === 'function' ? initial() : initial,
    direction: 'none' as 'none' | 'forward' | 'backward',
  }));
  const setIndex = (value: SetStateAction<number>) => setNavigation(previous => {
    const index = typeof value === 'function' ? value(previous.index) : value;
    return index === previous.index ? previous : { index, direction: index > previous.index ? 'forward' : 'backward' };
  });
  return { ...navigation, setIndex };
}
