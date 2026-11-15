// Inline SVG icons from the design review (stroke icons on a 24px grid).
import type { ReactNode } from 'react'

function Stroke({ size = 20, width = 2, children }: { size?: number; width?: number; children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  )
}

export const ChatIcon = ({ size }: { size?: number }) => (
  <Stroke size={size}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
  </Stroke>
)

export const SearchIcon = ({ size }: { size?: number }) => (
  <Stroke size={size}>
    <circle cx="11" cy="11" r="6" />
    <path d="m20 20-4-4" />
  </Stroke>
)

export const BackIcon = () => (
  <Stroke>
    <path d="m15 18-6-6 6-6" />
  </Stroke>
)

export const CloseIcon = () => (
  <Stroke>
    <path d="M6 6l12 12M18 6 6 18" />
  </Stroke>
)

export const MoreIcon = () => (
  <Stroke>
    <circle cx="5" cy="12" r="1" />
    <circle cx="12" cy="12" r="1" />
    <circle cx="19" cy="12" r="1" />
  </Stroke>
)

export const PhoneIcon = () => (
  <Stroke size={16}>
    <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" />
  </Stroke>
)

export const AssistantIcon = ({ size = 20 }: { size?: number }) => (
  <Stroke size={size} width={1.8}>
    <path d="M4 11a8 7 0 1 1 3.2 5.6L4 18l1-3.2A7 7 0 0 1 4 11Z" />
    <path d="M9 10.5v.5M15 10.5v.5" />
    <path d="M9.5 13.5c1.4 1 3.6 1 5 0" />
  </Stroke>
)

const categoryPaths: Record<string, ReactNode> = {
  '子育て・教育': (
    <>
      <circle cx="12" cy="7" r="3" />
      <path d="M6 21v-2a6 6 0 0 1 12 0v2" />
    </>
  ),
  '健康・医療': <path d="M12 21s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.6-7 10-7 10Z" />,
  '福祉・介護': (
    <>
      <path d="M7 11V8a5 5 0 0 1 10 0v3" />
      <rect x="5" y="11" width="14" height="9" rx="2" />
    </>
  ),
  '住まい・暮らし': (
    <>
      <path d="M4 11 12 4l8 7" />
      <path d="M6 10v10h12V10" />
    </>
  ),
  '届出・証明': (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M8 10h8M8 14h5" />
    </>
  ),
  '税・保険・年金': (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v8M9.5 10.5h4a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3h4" />
    </>
  ),
  '防災・安全': <path d="M12 3 4 6v6c0 4.4 3.4 8 8 9 4.6-1 8-4.6 8-9V6l-8-3Z" />,
  '仕事・産業': (
    <>
      <path d="M4 9h16v10H4z" />
      <path d="M9 9V6h6v3" />
    </>
  ),
}

const folder = <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />

export const CategoryIcon = ({ name, size = 24 }: { name: string; size?: number }) => (
  <Stroke size={size} width={1.8}>
    {categoryPaths[name] ?? folder}
  </Stroke>
)
