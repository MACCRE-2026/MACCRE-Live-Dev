import { X, Terminal } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function GlobalTelemetryBoard({ isOpen, onClose }: any) {
  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div 
        className="miniboard-slate global-telemetry"
        initial={{ y: 400, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 400, opacity: 0 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        style={{ right: '50%', transform: 'translateX(50%)', width: '800px', height: '600px', top: '10%' }}
      >
        <div className="miniboard-header" style={{ background: 'rgba(0, 255, 204, 0.1)', borderBottom: '1px solid var(--accent)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: 'var(--accent)' }}>
            <Terminal size={20} />
            <h3>Sanitized Swarm Telemetry (Smoke Test)</h3>
          </div>
          <button className="icon-btn" onClick={onClose}><X size={20} /></button>
        </div>

        <div className="miniboard-content" style={{ background: '#050508' }}>
          <div className="telemetry-box" style={{ height: '100%', border: 'none', background: 'transparent' }}>
            <div style={{ color: '#00ffcc', marginBottom: '8px' }}>[SYSTEM] Swarm ignited. Constructing active topological map...</div>
            <div style={{ color: '#aaa', marginBottom: '8px' }}>[ROUTER] START_NODE activated. Resolving Next_Node(s)...</div>
            <div style={{ color: '#aaa', marginBottom: '8px' }}>[ROUTER] Routing payload to: Agent_Alpha, Agent_Beta.</div>
            <div style={{ color: '#ff3366', marginBottom: '8px' }}>[AUDIO] Agent_Alpha connected to Live API.</div>
            <div style={{ color: '#ff3366', marginBottom: '8px' }}>[AUDIO] Agent_Beta connected to Live API.</div>
            <div style={{ color: '#fff', margin: '16px 0', paddingLeft: '16px', borderLeft: '2px solid #555' }}>
              <strong>Agent_Alpha:</strong> "I have reviewed the payload. Engaging synthesis protocol."
            </div>
            <div style={{ color: '#00ffcc', marginTop: 'auto' }}>[SYSTEM] Awaiting further topology state changes...</div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
