import { useCallback, useRef, useState } from 'react'
import { uploadPaper } from '@/api/client'
import { useAppStore } from '@/store/appStore'
import type { Paper } from '@/types'

interface UploadWidgetProps {
  className?: string
}

export default function UploadWidget({ className }: UploadWidgetProps) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const setPaper = useAppStore((s) => s.setPaper)

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setError('Only PDF files are supported')
        return
      }
      setError(null)
      setUploading(true)
      try {
        const res = await uploadPaper(file)
        const paper: Paper = {
          paper_id: res.paper_id,
          title: res.title,
          file_path: res.file_path,
          parsed_at: null,
        }
        setPaper(paper)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Upload failed')
      } finally {
        setUploading(false)
      }
    },
    [setPaper],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }, [])

  const handleDragLeave = useCallback(() => setDragOver(false), [])

  const handleClick = () => inputRef.current?.click()

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  return (
    <div
      className={`${className || ''} ${dragOver ? 'upload-widget--dragover' : ''}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') handleClick()
      }}
      aria-label="Upload a PDF paper"
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        border: `2px dashed ${dragOver ? '#2563eb' : '#d1d5db'}`,
        borderRadius: 12,
        backgroundColor: dragOver ? '#eff6ff' : 'transparent',
        cursor: 'pointer',
        transition: 'border-color 0.2s, background-color 0.2s',
        minHeight: 200,
        padding: 32,
        gap: 12,
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        style={{ display: 'none' }}
        onChange={handleInputChange}
      />
      {uploading ? (
        <p style={{ color: '#6b7280', fontSize: '1rem' }}>Uploading paper...</p>
      ) : (
        <>
          <p style={{ color: dragOver ? '#2563eb' : '#6b7280', fontSize: '1rem', fontWeight: 500 }}>
            {dragOver ? 'Drop your PDF here' : 'Upload a paper to get started'}
          </p>
          <p style={{ color: '#9ca3af', fontSize: '0.85rem' }}>
            Click to browse or drag and drop a PDF file
          </p>
        </>
      )}
      {error && (
        <p style={{ color: '#dc2626', fontSize: '0.85rem', marginTop: 8 }}>{error}</p>
      )}
    </div>
  )
}
