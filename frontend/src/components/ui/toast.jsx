import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { Button } from './button'

export function Toast({ message, type = 'success', onClose }) {
  const bgColor = type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-blue-500'

  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  return (
    <div className={`fixed top-4 right-4 ${bgColor} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 z-50 animate-in slide-in-from-right`}>
      <span>{message}</span>
      <Button
        onClick={onClose}
        variant="ghost"
        className="text-white hover:bg-white/20 p-1 h-auto"
      >
        <X className="w-4 h-4" />
      </Button>
    </div>
  )
}

export function useToast() {
  const [toast, setToast] = useState(null)

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
  }

  const hideToast = () => {
    setToast(null)
  }

  return { toast, showToast, hideToast }
}
