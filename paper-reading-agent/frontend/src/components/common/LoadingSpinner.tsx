export default function LoadingSpinner({ message = 'Loading...' }: { message?: string }) {
  return <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>{message}</div>
}
