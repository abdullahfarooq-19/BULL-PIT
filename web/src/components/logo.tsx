/** The Bull Pit mark: a white triangle on a black tile. The thin edge keeps the black
 *  tile visible on the dark page. Decorative: the name is always written beside it. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <rect x="0.5" y="0.5" width="31" height="31" rx="7" fill="#000" stroke="#2a3038" />
      <path d="M16 8 25 23H7Z" fill="#fff" />
    </svg>
  );
}
