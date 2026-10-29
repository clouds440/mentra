/** Bounded arithmetic grammar, never JavaScript or dynamically evaluated code. */
export const chartNumberLimit = 1e100;
export const finiteChartNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= chartNumberLimit;
const functions = new Map<string, { min: number; max: number; run: (...args: number[]) => number }>([
  ...Object.entries({ abs: Math.abs, sqrt: Math.sqrt, sin: Math.sin, cos: Math.cos, tan: Math.tan, log: Math.log, ln: Math.log, exp: Math.exp, round: Math.round, floor: Math.floor, ceil: Math.ceil }).map(([name, run]) => [name, { min: 1, max: 1, run }] as const),
  ['pow', { min: 2, max: 2, run: Math.pow }], ['min', { min: 2, max: 8, run: Math.min }], ['max', { min: 2, max: 8, run: Math.max }],
]);
const constants = new Map([['pi', Math.PI], ['e', Math.E]]);
export const equationIdentifier = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(value) && !['constructor', 'prototype', '__proto__'].includes(value) && !functions.has(value) && !constants.has(value);
type Node = { kind: 'number'; value: number } | { kind: 'name'; name: string } | { kind: 'unary'; sign: string; child: Node } | { kind: 'binary'; op: string; left: Node; right: Node } | { kind: 'call'; name: string; args: Node[] };
export type CompiledEquation = { references: Set<string>; constants: Set<string>; calculate: (scope: ReadonlyMap<string, number>) => number };
export function compileEquation(source: string): CompiledEquation {
  if (!source.trim() || source.length > 240) throw new Error('Equation is too large');
  const scanner = /\s*((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[A-Za-z][A-Za-z0-9_]*|\*\*|[+*/^(),-])/y;
  const tokens: string[] = []; let at = 0;
  while (source.slice(at).trim()) {
    scanner.lastIndex = at; const match = scanner.exec(source);
    if (!match || tokens.length >= 128) throw new Error('Unsupported equation syntax');
    tokens.push(match[1]); at = scanner.lastIndex;
  }
  let cursor = 0; const references = new Set<string>(); const usedConstants = new Set<string>();
  function parse(minimum = 0, depth = 0): Node {
    if (depth > 32) throw new Error('Equation nesting is too deep');
    const token = tokens[cursor++]; let left: Node;
    if (token === '+' || token === '-') left = { kind: 'unary', sign: token, child: parse(25, depth + 1) };
    else if (token === '(') { left = parse(0, depth + 1); if (tokens[cursor++] !== ')') throw new Error('Missing parenthesis'); }
    else if (token && /^(?:\d|\.)/.test(token)) {
      const value = Number(token); if (!Number.isFinite(value)) throw new Error('Invalid number');
      left = { kind: 'number', value };
    } else if (token && /^[A-Za-z]/.test(token)) {
      if (tokens[cursor] === '(') {
        const fn = functions.get(token); if (!fn) throw new Error('Unsupported function');
        cursor++; const args: Node[] = [];
        if (tokens[cursor] !== ')') {
          do { if (args.length >= fn.max) throw new Error('Too many arguments'); args.push(parse(0, depth + 1)); } while (tokens[cursor] === ',' && ++cursor);
        }
        if (tokens[cursor++] !== ')' || args.length < fn.min) throw new Error('Invalid arguments');
        left = { kind: 'call', name: token, args };
      } else {
        if (!constants.has(token) && !equationIdentifier(token)) throw new Error('Invalid variable');
        if (!constants.has(token)) references.add(token); else usedConstants.add(token);
        left = { kind: 'name', name: token };
      }
    } else throw new Error('Expected a number, variable or parenthesis');
    while (cursor < tokens.length) {
      const op = tokens[cursor]; const precedence = op === '+' || op === '-' ? 10 : op === '*' || op === '/' ? 20 : op === '^' || op === '**' ? 30 : -1;
      if (precedence < minimum) break;
      cursor++; left = { kind: 'binary', op, left, right: parse(precedence + (precedence === 30 ? 0 : 1), depth + 1) };
    }
    return left;
  }
  const tree = parse(); if (cursor !== tokens.length) throw new Error('Unexpected equation input');
  const checked = (value: number) => { if (!Number.isFinite(value)) throw new Error('Equation intermediate value is outside its domain'); return value; };
  function evaluate(node: Node, scope: ReadonlyMap<string, number>): number {
    if (node.kind === 'number') return node.value;
    if (node.kind === 'name') { const value = constants.get(node.name) ?? scope.get(node.name); if (value === undefined || !Number.isFinite(value)) throw new Error('Unknown or invalid variable'); return value; }
    if (node.kind === 'unary') return checked((node.sign === '-' ? -1 : 1) * evaluate(node.child, scope));
    if (node.kind === 'call') return checked(functions.get(node.name)!.run(...node.args.map(arg => evaluate(arg, scope))));
    const left = evaluate(node.left, scope), right = evaluate(node.right, scope);
    return checked(node.op === '+' ? left + right : node.op === '-' ? left - right : node.op === '*' ? left * right : node.op === '/' ? left / right : Math.pow(left, right));
  }
  return { references, constants: usedConstants, calculate: scope => { const value = evaluate(tree, scope); if (!finiteChartNumber(value)) throw new Error('Equation result is outside the supported domain'); return value; } };
}
