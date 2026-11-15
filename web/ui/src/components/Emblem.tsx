// The city emblem (docs/assets/city-emblem.svg), drawn in currentColor.
export default function Emblem({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" role="img" aria-label="出茂市の市章" className="emblem">
      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
        <path d="M69.72 12.92A42 42 0 1 1 30.28 12.92" strokeWidth="9" />
        <path d="M50 72V24" strokeWidth="8" />
        <path d="M36 31V44Q36 50 42 50H58Q64 50 64 44V31" strokeWidth="8" />
        <path d="M28 55V66Q28 72 34 72H66Q72 72 72 66V55" strokeWidth="8" />
      </g>
      <g fill="currentColor">
        <path d="M50 24C51 15 57 10 64 10C63 18 57 23 50 24Z" />
        <path d="M50 24C49 15 43 10 36 10C37 18 43 23 50 24Z" />
      </g>
    </svg>
  )
}
