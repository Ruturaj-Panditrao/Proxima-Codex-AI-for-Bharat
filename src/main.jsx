import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import VoiceApp from './components/VoiceApp.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <VoiceApp/>
  </StrictMode>,
)
