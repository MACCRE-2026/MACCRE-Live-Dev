import { X, KeyRound, CloudUpload, ShieldCheck, ListChecks } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function AuthPanel({ isOpen, onClose }: any) {
  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div 
        className="miniboard-slate ancillary-popout"
        initial={{ x: 300, opacity: 0 }}
        animate={{ x: -832, opacity: 1 }} // Slide to the left of the Agent Studio Settings (400 + 400 + 32px gap)
        exit={{ x: 300, opacity: 0 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        style={{ zIndex: 198, height: 'calc(100vh - 200px)', top: '64px' }}
      >
        <div className="miniboard-header" style={{ background: 'rgba(255, 184, 108, 0.1)', borderBottom: '1px solid #ffb86c' }}>
          <h3 style={{ color: '#ffb86c' }}><ShieldCheck size={18} style={{ display: 'inline', verticalAlign: 'text-bottom' }}/> Vault & Instructions</h3>
          <button className="icon-btn" onClick={onClose}><X size={20} /></button>
        </div>

        <div className="miniboard-content">
          <div className="slate-section">
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#ffb86c' }}>
              <KeyRound size={16} /> Multi-Cloud Vault (Auth)
            </label>
            <p className="system-msg" style={{ fontSize: '0.75rem', marginBottom: '8px' }}>
              Securely inject external credentials into the MACCREv2 Datacenter DPAPI vault.
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="btn-secondary" style={{ flex: 1, padding: '8px' }} title="Ingest OAuth Token">
                Ingest OAuth
              </button>
              <button className="btn-secondary" style={{ flex: 1, padding: '8px', border: '1px solid #ffb86c', color: '#ffb86c' }} title="Upload Vertex Service Account JSON">
                <CloudUpload size={16} style={{ display: 'inline', marginRight: '4px' }}/> Vertex JSON
              </button>
            </div>
          </div>

          <div className="slate-section" style={{ flex: 1 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ListChecks size={16} /> Instruction Checklist
            </label>
            <p className="system-msg" style={{ fontSize: '0.75rem', marginBottom: '8px' }}>
              Global directives to enforce on this session.
            </p>
            <div className="live-roster-checklist" style={{ flex: 1, maxHeight: 'none', border: '1px solid var(--panel-border)', borderRadius: '4px', padding: '8px' }}>
              <label className="checklist-item">
                <input type="checkbox" defaultChecked />
                Enforce Zero-Markdown Output
              </label>
              <label className="checklist-item">
                <input type="checkbox" defaultChecked />
                Enforce JSON Schema Validations
              </label>
              <label className="checklist-item">
                <input type="checkbox" />
                Verbose Telemetry Logging
              </label>
              <label className="checklist-item">
                <input type="checkbox" />
                Suppress Transient Model Failover Alerts
              </label>
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
