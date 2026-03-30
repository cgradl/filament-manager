import { createPortal } from 'react-dom'

export default function Modal({ children }: { children: React.ReactNode }) {
  return createPortal(children, document.body)
}
