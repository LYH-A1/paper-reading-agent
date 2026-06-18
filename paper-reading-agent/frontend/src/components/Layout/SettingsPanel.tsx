import { useState, useEffect } from 'react'
import { getPreferences, putPreferences, type Preferences } from '@/api/client'
import styles from './Layout.module.css'

export default function SettingsPanel() {
  const [open, setOpen] = useState(false)
  const [prefs, setPrefs] = useState<Preferences | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (open && !prefs) {
      getPreferences()
        .then(setPrefs)
        .catch(() => setMessage('Failed to load preferences'))
    }
  }, [open, prefs])

  const handleSave = async () => {
    if (!prefs) return
    setSaving(true)
    setMessage('')
    try {
      await putPreferences(prefs)
      setMessage('Saved!')
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Save failed')
    }
    setSaving(false)
  }

  return (
    <div className={styles.settingsPanel}>
      <button
        className={styles.settingsToggle}
        onClick={() => setOpen(!open)}
      >
        {open ? '▼' : '▶'} Settings
      </button>

      {open && prefs && (
        <div className={styles.settingsForm}>
          <label>
            Reranker
            <select
              value={prefs.reranker}
              onChange={(e) => setPrefs({ ...prefs, reranker: e.target.value })}
            >
              <option value="flashrank">FlashRank</option>
              <option value="bm25">BM25</option>
            </select>
          </label>

          <label>
            Top-K Results
            <input
              type="number"
              min={1}
              max={20}
              value={prefs.top_k}
              onChange={(e) => setPrefs({ ...prefs, top_k: Number(e.target.value) })}
            />
          </label>

          <label>
            Language
            <select
              value={prefs.language}
              onChange={(e) => setPrefs({ ...prefs, language: e.target.value })}
            >
              <option value="auto">Auto</option>
              <option value="en">English</option>
              <option value="zh">Chinese</option>
            </select>
          </label>

          <label>
            Embedding Model
            <input
              type="text"
              value={prefs.embedding_model}
              onChange={(e) => setPrefs({ ...prefs, embedding_model: e.target.value })}
            />
          </label>

          <button
            className={styles.settingsSaveBtn}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>

          {message && <span className={styles.settingsMsg}>{message}</span>}
        </div>
      )}
    </div>
  )
}
