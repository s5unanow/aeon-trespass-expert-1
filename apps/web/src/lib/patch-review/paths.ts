function escapePointerToken(token: string | number): string {
  return String(token).replace(/~/g, '~0').replace(/\//g, '~1');
}

export function buildJsonPointer(...tokens: (string | number)[]): string {
  return `/${tokens.map(escapePointerToken).join('/')}`;
}

export function buildBlockPath(blockIndex: number, ...tokens: (string | number)[]): string {
  return buildJsonPointer('blocks', blockIndex, ...tokens);
}

export function resolveJsonPointer(data: unknown, pointer: string): unknown {
  if (pointer === '') return data;
  if (!pointer.startsWith('/')) {
    throw new Error(`JSON Pointer must start with "/": ${pointer}`);
  }
  return pointer
    .slice(1)
    .split('/')
    .map((token) => token.replace(/~1/g, '/').replace(/~0/g, '~'))
    .reduce<unknown>((current, token) => {
      if (Array.isArray(current)) {
        const index = Number(token);
        if (!Number.isInteger(index) || index < 0 || index >= current.length) {
          throw new Error(`Array index out of bounds: ${token}`);
        }
        return current[index];
      }
      if (current && typeof current === 'object' && token in current) {
        return (current as Record<string, unknown>)[token];
      }
      throw new Error(`JSON Pointer segment does not resolve: ${token}`);
    }, data);
}
