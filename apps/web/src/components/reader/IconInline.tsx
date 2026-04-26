import { useNavigate, useParams } from 'react-router';
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
  const navigate = useNavigate();
  const { documentId, edition } = useParams<{ documentId: string; edition: string }>();

  if (HIDDEN_ICONS.has(symbolId)) {
    return null;
  }

  const label = alt || symbolId.replace('sym.', '');
  const src = ICON_MAP[symbolId];
  const entry = glossary.get(symbolId);
  const tooltip = entry
    ? entry.source_term
      ? `${entry.source_term} — ${entry.notes ?? entry.preferred_term}`
      : (entry.notes ?? entry.preferred_term)
    : undefined;

  // Click handler navigates to the glossary deep-link if we have an entry +
  // edition + documentId. Without those, the icon stays non-interactive.
  const conceptId = entry?.concept_id;
  const canNavigate = !!conceptId && !!documentId && !!edition;
  const targetPath = canNavigate
    ? `/documents/${documentId}/${edition}/glossary#${conceptId}`
    : undefined;
  const onClick = canNavigate
    ? (e: React.MouseEvent<HTMLElement>) => {
        e.preventDefault();
        navigate(targetPath!);
      }
    : undefined;
  const onKeyDown = canNavigate
    ? (e: React.KeyboardEvent<HTMLElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          navigate(targetPath!);
        }
      }
    : undefined;
  const role = canNavigate ? 'link' : undefined;
  const tabIndex = canNavigate ? 0 : undefined;
  const ariaLabel = canNavigate
    ? `${label} — open glossary entry`
    : undefined;
  const className = [
    'icon-inline-wrapper',
    tooltip ? 'glossary-tooltip' : '',
    canNavigate ? 'glossary-keyword' : '',
  ]
    .filter(Boolean)
    .join(' ');

  if (src) {
    return (
      <span
        className={className || undefined}
        data-tooltip={tooltip}
        data-concept-id={conceptId}
        onClick={onClick}
        onKeyDown={onKeyDown}
        role={role}
        tabIndex={tabIndex}
        aria-label={ariaLabel}
      >
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
      className={`icon-inline${tooltip ? ' glossary-tooltip' : ''}${canNavigate ? ' glossary-keyword' : ''}`}
      role={canNavigate ? 'link' : 'img'}
      aria-label={ariaLabel ?? label}
      data-symbol-id={symbolId}
      data-concept-id={conceptId}
      title={tooltip ?? label}
      data-tooltip={tooltip}
      onClick={onClick}
      onKeyDown={onKeyDown}
      tabIndex={tabIndex}
    >
      [{label}]
    </span>
  );
}
