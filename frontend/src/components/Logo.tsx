/**
 * The SCRPT logo — a spaced wordmark, no symbol.
 * Inherits currentColor (rendered bronze via text-accent in the chrome).
 */

export function ScrptLogo({ size = 22, tagline = false }: {
  size?: number; tagline?: boolean;
}) {
  return (
    <span className="inline-flex flex-col select-none" style={{ lineHeight: 1, gap: tagline ? 6 : 0 }}>
      <span
        className="serif-display font-semibold"
        style={{ fontSize: size, letterSpacing: "0.3em", marginRight: "-0.3em" }}
      >
        SCRPT
      </span>
      {tagline && (
        <span
          className="uppercase"
          style={{
            fontSize: size * 0.32,
            letterSpacing: "0.42em",
            opacity: 0.55,
            fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
          }}
        >
          Write · Publish · Sell
        </span>
      )}
    </span>
  );
}
