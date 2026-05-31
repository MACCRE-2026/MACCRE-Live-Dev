import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function SwarmMonitorTerminal({ isOpen, onClose, activeNodes, onNudgeRequest }: any) {
  const [globalLogs, setGlobalLogs] = useState<string[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    const interval = setInterval(() => {
      fetch('http://127.0.0.1:8000/api/telemetry')
        .then(res => res.json())
        .then(data => setGlobalLogs(data))
        .catch(console.error);
    }, 2000);
    return () => clearInterval(interval);
  }, [isOpen]);

  if (!isOpen) return null;

  // Fallback if no agents exist in the topology yet
  const displayNodes = activeNodes.length > 0 ? activeNodes : [
    { id: 'alpha', data: { label: 'Agent_Alpha' } },
    { id: 'beta', data: { label: 'Agent_Beta' } }
  ];

  return (
    <AnimatePresence>
      <motion.div 
        className="miniboard-slate"
        initial={{ y: -50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: -50, opacity: 0 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        style={{ 
          right: '5%', 
          left: '5%',
          width: '90%', 
          height: '80vh', 
          top: '10vh',
          zIndex: 999,
          boxShadow: '0 32px 128px rgba(0,0,0,0.8)'
        }}
      >
        <div className="miniboard-header" style={{ background: 'rgba(0,0,0,0.5)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: 'var(--accent)' }}>
            <h3 style={{ textTransform: 'uppercase', letterSpacing: '1px' }}>Global Swarm Monitor Terminal</h3>
          </div>
          <button className="icon-btn" onClick={onClose}><X size={24} /></button>
        </div>

        <div className="miniboard-content" style={{ display: 'flex', flexDirection: 'row', gap: '16px', padding: '16px', background: '#0a0a0f', overflowX: 'auto' }}>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minWidth: '400px', flex: 1, background: 'rgba(0,0,0,0.6)', border: '1px solid #333', borderRadius: '8px' }}>
            <div style={{ padding: '12px', background: '#1a1a24', borderBottom: '1px solid #333', fontWeight: 'bold', color: 'var(--accent)', display: 'flex', justifyContent: 'center' }}>
              GLOBAL LIVE TELEMETRY
            </div>
            <div style={{ flex: 1, padding: '16px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.85rem', color: '#ccc', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {globalLogs.length > 0 ? (
                globalLogs.map((log, idx) => (
                  <div key={idx} style={{ borderLeft: '2px solid #555', paddingLeft: '8px' }}>{log}</div>
                ))
              ) : (
                <div style={{ color: '#666', fontStyle: 'italic' }}>[Awaiting Build Pipeline Stream...]</div>
              )}
            </div>
          </div>

          {displayNodes.map((node: any) => (
            <div key={node.id} style={{ flex: 1, minWidth: '300px', display: 'flex', flexDirection: 'column', border: '1px solid #333', borderRadius: '8px', background: 'rgba(0,0,0,0.6)' }}>
              
              <div style={{ padding: '12px', background: '#1a1a24', borderBottom: '1px solid #333', fontWeight: 'bold', color: '#ccc', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <div className="status-dot live" style={{ marginRight: '8px' }} />
                  {node.data.label}
                </div>
                {onNudgeRequest && (
                  <button 
                    className="btn-secondary" 
                    style={{ padding: '4px 8px', fontSize: '0.75rem' }}
                    onClick={() => onNudgeRequest(node.id)}
                  >
                    Nudge
                  </button>
                )}
              </div>

              <div style={{ flex: 1, padding: '16px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px', fontFamily: 'monospace', fontSize: '0.85rem' }}>
                <div style={{ color: '#666', fontStyle: 'italic' }}>[Awaiting Agent Ledger Stream...]</div>
              </div>
            </div>
          ))}

        </div>
      </motion.div>
    </AnimatePresence>
  );
}
