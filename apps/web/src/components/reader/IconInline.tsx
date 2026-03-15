interface IconInlineProps {
  symbolId: string;
  alt?: string;
}

export function IconInline({ symbolId, alt }: IconInlineProps) {
  // For now, render as a styled span with the symbol id.
  // In production, this would reference a sprite sheet or asset catalog.
  const label = alt || symbolId.replace('sym.', '');
  return (
    <span
      className="icon-inline"
      role="img"
      aria-label={label}
      data-symbol-id={symbolId}
      title={label}
    >
      ⬢
    </span>
  );
}
