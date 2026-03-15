interface SourcePageBadgeProps {
  pageNumber: number;
}

export function SourcePageBadge({ pageNumber }: SourcePageBadgeProps) {
  return (
    <span className="source-page-badge" aria-label={`Source page ${pageNumber}`}>
      p.{pageNumber}
    </span>
  );
}
