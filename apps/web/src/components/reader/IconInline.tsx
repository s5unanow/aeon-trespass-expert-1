interface IconInlineProps {
  symbolId: string;
  alt?: string;
}

const ICON_MAP: Record<string, string> = {
  'sym.danger': '/icons/stat_danger.png',
  'sym.fate': '/icons/stat_fate.png',
  'sym.rage': '/icons/stat_rage.png',
  'sym.progress': '/icons/stat_progress.png',
  'sym.doom': '/icons/stat_doom.png',
  'sym.crew': '/icons/stat_crew.png',
  'sym.hull': '/icons/stat_hull.png',
  'sym.argo_fate': '/icons/stat_argo_fate.png',
  'sym.argo_knowledge': '/icons/stat_argo_knowledge.png',
};

export function IconInline({ symbolId, alt }: IconInlineProps) {
  const label = alt || symbolId.replace('sym.', '');
  const src = ICON_MAP[symbolId];

  if (src) {
    return (
      <img
        className="icon-inline"
        src={src}
        alt={label}
        title={label}
        data-symbol-id={symbolId}
        style={{ height: '1em', verticalAlign: 'middle', display: 'inline' }}
      />
    );
  }

  return (
    <span
      className="icon-inline"
      role="img"
      aria-label={label}
      data-symbol-id={symbolId}
      title={label}
    >
      [{label}]
    </span>
  );
}
