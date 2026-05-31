import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FolderSearch, FileSearch, Send } from 'lucide-react';

interface NudgeModalProps {
  isOpen: boolean;
  onClose: () => void;
  targetNode: string | null; // null means 'ALL'
  onSubmit: (target: string, payload: string) => void;
}

export default function NudgeModal({ isOpen, onClose, targetNode, onSubmit }: NudgeModalProps) {
  const [payloadText, setPayloadText] = useState("");

  const handlePicker = async (type: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/picker?type=${type}`);
      const data = await res.json();
      if (data.path) {
        setPayloadText(data.path);
      }
    } catch (e) {
      console.error("Picker failed", e);
    }
  };

  const handleSubmit = () => {
    onSubmit(targetNode || "ALL", payloadText);
    setPayloadText("");
    onClose();
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div 
        className="modal-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        <motion.div 
          className="modal-content"
          initial={{ y: 50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 50, opacity: 0 }}
          style={{
            background: 'var(--panel-bg)',
            border: '1px solid var(--panel-border)',
            borderRadius: '12px',
            width: '400px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '16px', borderBottom: '1px solid var(--panel-border)', background: 'rgba(255,255,255,0.02)' }}>
            <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--accent)' }}>
              {targetNode ? `Nudge Agent: ${targetNode}` : 'Global Swarm Nudge'}
            </h3>
            <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer' }}><X size={20} /></button>
          </div>
          
          <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <p style={{ margin: 0, fontSize: '0.9rem', color: '#aaa' }}>
              Inject a context override into the {targetNode ? 'active node' : 'entire running swarm'}.
            </p>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontSize: '0.85rem', color: '#ccc' }}>Payload Directive (Path or Text)</label>
              <textarea 
                value={payloadText}
                onChange={(e) => setPayloadText(e.target.value)}
                placeholder="Type a manual directive, or select a file/folder path..."
                style={{
                  width: '100%',
                  height: '80px',
                  background: 'rgba(0,0,0,0.3)',
                  border: '1px solid var(--panel-border)',
                  color: 'white',
                  borderRadius: '4px',
                  padding: '8px',
                  resize: 'none'
                }}
              />
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                <button className="btn-secondary" onClick={() => handlePicker('file')} title="Attach File">
                  <FileSearch size={16} style={{ marginRight: '6px' }} /> File
                </button>
                <button className="btn-secondary" onClick={() => handlePicker('folder')} title="Attach Folder">
                  <FolderSearch size={16} style={{ marginRight: '6px' }} /> Folder
                </button>
              </div>
            </div>
          </div>

          <div style={{ padding: '16px', borderTop: '1px solid var(--panel-border)', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn-primary" onClick={handleSubmit} disabled={!payloadText.trim()} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Send size={16} /> Send Nudge
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
