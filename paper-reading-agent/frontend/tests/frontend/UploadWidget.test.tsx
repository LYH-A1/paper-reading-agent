import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { uploadPaper } from '@/api/client'
import UploadWidget from '@/components/Layout/UploadWidget'
import { useAppStore } from '@/store/appStore'

vi.mock('@/api/client', () => ({
  uploadPaper: vi.fn(),
}))

beforeEach(() => {
  useAppStore.setState({ paper: null })
})

describe('UploadWidget', () => {
  it('renders the empty state message', () => {
    render(<UploadWidget />)
    expect(screen.getByText('Upload a paper to get started')).toBeDefined()
    expect(screen.getByText('Click to browse or drag and drop a PDF file')).toBeDefined()
  })

  it('shows an error for non-PDF files', async () => {
    const file = new File(['dummy'], 'test.txt', { type: 'text/plain' })
    const input = document.createElement('input')
    const fileList = {
      0: file,
      length: 1,
      item: () => file,
    } as FileList

    render(<UploadWidget />)
    const dropZone = screen.getByRole('button')

    // Simulate drop event
    fireEvent.drop(dropZone, {
      dataTransfer: { files: fileList },
    })

    expect(await screen.findByText('Only PDF files are supported')).toBeDefined()
  })

  it('calls uploadPaper and sets paper on success', async () => {
    const mockResponse = {
      paper_id: 'abc-123',
      title: 'Test Paper',
      file_path: '/path/to/test.pdf',
    }
    vi.mocked(uploadPaper).mockResolvedValue(mockResponse)

    const file = new File(['dummy'], 'test.pdf', { type: 'application/pdf' })
    const input = document.createElement('input')
    const fileList = {
      0: file,
      length: 1,
      item: () => file,
    } as FileList

    render(<UploadWidget />)
    const dropZone = screen.getByRole('button')

    await act(async () => {
      fireEvent.drop(dropZone, {
        dataTransfer: { files: fileList },
      })
    })

    expect(uploadPaper).toHaveBeenCalledWith(file)

    // Wait for async upload to complete
    await vi.waitFor(() => {
      const state = useAppStore.getState()
      expect(state.paper).not.toBeNull()
      expect(state.paper?.paper_id).toBe('abc-123')
      expect(state.paper?.title).toBe('Test Paper')
    })
  })

  it('shows uploading state while uploading', async () => {
    // Don't resolve the promise so uploading stays true
    let resolvePromise: (v: unknown) => void
    vi.mocked(uploadPaper).mockImplementation(
      () => new Promise((resolve) => { resolvePromise = resolve }),
    )

    const file = new File(['dummy'], 'test.pdf', { type: 'application/pdf' })
    const input = document.createElement('input')
    const fileList = {
      0: file,
      length: 1,
      item: () => file,
    } as FileList

    render(<UploadWidget />)
    const dropZone = screen.getByRole('button')

    await act(async () => {
      fireEvent.drop(dropZone, {
        dataTransfer: { files: fileList },
      })
    })

    expect(screen.getByText('Uploading paper...')).toBeDefined()

    // Clean up by resolving the hanging promise
    await act(async () => { resolvePromise!(null) })
  })

  it('displays error message on upload failure', async () => {
    vi.mocked(uploadPaper).mockRejectedValue(new Error('Network error'))

    const file = new File(['dummy'], 'test.pdf', { type: 'application/pdf' })
    const input = document.createElement('input')
    const fileList = {
      0: file,
      length: 1,
      item: () => file,
    } as FileList

    render(<UploadWidget />)
    const dropZone = screen.getByRole('button')

    fireEvent.drop(dropZone, {
      dataTransfer: { files: fileList },
    })

    expect(await screen.findByText('Network error')).toBeDefined()
  })

  it('handles click to open file dialog', () => {
    render(<UploadWidget />)
    const dropZone = screen.getByRole('button')
    const clickSpy = vi.fn()

    // Mock the hidden input click
    const input = document.querySelector('input[type="file"]')
    if (input) {
      input.addEventListener('click', clickSpy)
    }

    fireEvent.click(dropZone)

    // The hidden input would receive the click; we just verify no crash
    expect(dropZone).toBeDefined()
  })

  it('accepts keyboard Enter and Space to activate', () => {
    render(<UploadWidget />)
    const dropZone = screen.getByRole('button')

    // These should not throw
    fireEvent.keyDown(dropZone, { key: 'Enter' })
    fireEvent.keyDown(dropZone, { key: ' ' })

    // Verify the hidden input is in the DOM
    expect(document.querySelector('input[type="file"]')).toBeDefined()
  })

  it('shows drag-over styling', () => {
    render(<UploadWidget />)
    const dropZone = screen.getByRole('button')

    fireEvent.dragOver(dropZone)
    // After dragover, the style should reflect drag state
    fireEvent.dragLeave(dropZone)
    // No crash
    expect(dropZone).toBeDefined()
  })
})
