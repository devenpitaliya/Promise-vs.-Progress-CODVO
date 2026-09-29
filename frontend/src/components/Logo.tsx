export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 42 42" fill="none" aria-hidden="true">
      <path d="M10 9L21 21L10 33L4 27L11 21L4 15L10 9Z" fill="#315BEF" />
      <path d="M32 9L26 15L31 21L26 27L32 33L38 21L32 9Z" fill="#284FD8" />
      <path d="M17 19H25V23H17V19Z" fill="#6086FF" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="text-[17px] font-bold tracking-tight text-ink">
      Promise <span className="text-brand">vs.</span> Progress
    </span>
  );
}
