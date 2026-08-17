/**
 * The SCRPT mark — a pen nib rising from an open book.
 * Minimal line work, monochrome, drawn in currentColor so it inherits
 * white-on-black anywhere it's placed.
 */

export function ScrptSymbol({ size = 28, strokeWidth = 3.2 }: {
  size?: number; strokeWidth?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden
    >
      {/* open book */}
      <path
        d="M6 47 C 15 41, 25 41.5, 32 46.5 C 39 41.5, 49 41, 58 47"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      {/* nib */}
      <path
        d="M32 8 L39.5 21 L32 38.5 L24.5 21 Z"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
      {/* slit */}
      <path
        d="M32 38.5 L32 20"
        stroke="currentColor"
        strokeWidth={strokeWidth * 0.72}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function ScrptLogo({ size = 22, withWordmark = true, tagline = false }: {
  size?: number; withWordmark?: boolean; tagline?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-3 select-none" style={{ lineHeight: 1 }}>
      <ScrptSymbol size={size * 1.35} />
      {withWordmark && (
        <span className="inline-flex flex-col" style={{ gap: tagline ? 5 : 0 }}>
          <span
            className="font-semibold"
            style={{
              fontSize: size,
              letterSpacing: "0.34em",
              marginRight: "-0.34em",
              fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
            }}
          >
            SCRPT
          </span>
          {tagline && (
            <span
              className="uppercase"
              style={{ fontSize: size * 0.36, letterSpacing: "0.4em",
                       opacity: 0.55, fontFamily: "var(--font-geist-sans), system-ui, sans-serif" }}
            >
              Write · Publish · Sell
            </span>
          )}
        </span>
      )}
    </span>
  );
}
