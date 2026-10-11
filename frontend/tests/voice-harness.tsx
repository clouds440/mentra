import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ChatComposer } from '../src/components/chat/ChatComposer';
import '../src/styles/global.css';

function Harness() {
  const [draft, setDraft] = useState('');
  const [sent, setSent] = useState('');
  const [chat, setChat] = useState(0);
  return <div className="mx-auto max-w-2xl p-3"><ChatComposer key={chat} value={draft} onChange={setDraft}
    onSubmit={() => { setSent(draft); setDraft(''); }} isThinking={false} onFiles={() => {}}
    selection={{ mode: 'STANDARD', document_ids: [] }} onSelectionChange={() => {}} />
    <p data-testid="sent">{sent}</p><button onClick={() => { setChat(chat+1); setDraft(''); }}>Switch chat</button></div>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
