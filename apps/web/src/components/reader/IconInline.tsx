import { useGlossary } from '../../contexts/GlossaryContext';

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
  'sym.evasion_dice': '/icons/stat_evasion_dice.png',
  'sym.evasion_difficulty': '/icons/stat_evasion_difficulty.png',
  'sym.knockback': '/icons/stat_knockback.png',
  'sym.priority_target': '/icons/stat_priority_target.png',
};

// Decorative/structural icons that should not be rendered inline
const HIDDEN_ICONS = new Set([
  'sym.board_tile_a',
  'sym.board_tile_c',
  'sym.board_tile_e',
  'sym.board_tile_f',
  'sym.board_tile_g',
  'sym.board_tile_h',
  'sym.board_tile_i',
  'sym.board_tile_n',
  'sym.art_ruins_ref',
  'sym.art_ruins_dark',
  'sym.art_ruins_small_b',
  'sym.art_ruins_small_c',
  'sym.art_texture_light_a',
  'sym.art_texture_light_b',
  'sym.marker_dark',
  'sym.crown_laurel_a',
  'sym.crown_laurel_b',
  'sym.terrain_city_a',
  'sym.terrain_glacier',
  'sym.terrain_cliff',
  'sym.titan_helmet',
  'sym.die_red',
]);

export function IconInline({ symbolId, alt }: IconInlineProps) {
  const glossary = useGlossary();

  if (HIDDEN_ICONS.has(symbolId)) {
    return null;
  }

  const label = alt || symbolId.replace('sym.', '');
  const src = ICON_MAP[symbolId];
  const entry = glossary.get(symbolId);
  const tooltip = entry
    ? `${entry.source_term ?? ''} — ${entry.notes ?? entry.preferred_term}`
    : undefined;

  if (src) {
    return (
      <span className={tooltip ? 'glossary-tooltip' : undefined} data-tooltip={tooltip}>
        <img
          className="icon-inline"
          src={src}
          alt={label}
          title={tooltip ?? label}
          data-symbol-id={symbolId}
          style={{ height: '1em', verticalAlign: 'middle', display: 'inline' }}
        />
      </span>
    );
  }

  return (
    <span
      className={`icon-inline${tooltip ? ' glossary-tooltip' : ''}`}
      role="img"
      aria-label={label}
      data-symbol-id={symbolId}
      title={tooltip ?? label}
      data-tooltip={tooltip}
    >
      [{label}]
    </span>
  );
}
