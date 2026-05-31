import { useState, useEffect } from 'react';
import { X, Settings2, Users, ChevronRight, ChevronLeft, FolderSearch, FileSearch } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import AgentStudioSettings from './AgentStudioSettings';
import AuthPanel from './AuthPanel';

export default function Miniboard({ agent, onClose, allNodes, onUpdateNode, onUpdateMultipleNodes }: any) {
  const [instruction, setInstruction] = useState(agent?.data?.instruction || "You are a helpful assistant.");
  const [model, setModel] = useState("");
  const [tools, setTools] = useState("");
  const [description, setDescription] = useState("");
  const [payload, setPayload] = useState(agent?.data?.payload || "");

  const [showStudio, setShowStudio] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [globalAgents, setGlobalAgents] = useState<any[]>([]);

  const [selectedAgentName, setSelectedAgentName] = useState(
    agent?.data?.label === 'WAIT/RETRY' || agent?.data?.label === 'HUMAN_GATE' 
      ? "Unassigned Agent" 
      : (agent?.data?.label || "Unassigned Agent")
  );
  
  const [nodeType, setNodeType] = useState(
    agent?.data?.label === 'WAIT/RETRY' ? 'WAIT/RETRY' :
    agent?.data?.label === 'HUMAN_GATE' ? 'HUMAN_GATE' : 'AGENT'
  );

  const handleAgentSelect = (e: any) => {
    const val = e.target.value;
    setSelectedAgentName(val);
    
    const found = globalAgents.find(a => a.Agent_Name === val);
    if (found) {
      setInstruction(found.System_Prompt || "");
      setModel(found.Model || "");
      setTools(found.Tools_Allowed || "");
      setDescription(found.Description || "");
    }
  };

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/rosters')
      .then(res => res.json())
      .then(data => {
        // Backend returns { "GLOBAL": [agents], ... }
        if (data.GLOBAL) {
          setGlobalAgents(data.GLOBAL);
        } else {
          // If the backend flattens it or still has old projects, just merge them all for now
          const merged = Object.values(data).flat();
          setGlobalAgents(merged);
        }
      })
      .catch(console.error);
  }, []);

  const isLoop = nodeType === 'WAIT/RETRY' || agent?.type === 'loopNode';

  const [recursionVal, setRecursionVal] = useState(agent?.data?.recursion || 3);
  const [liveStatuses, setLiveStatuses] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (isLoop && agent) {
      const initial: Record<string, boolean> = {};
      allNodes.forEach((n: any) => { if (n.id !== agent.id) initial[n.id] = n.data.isLive || false; });
      setLiveStatuses(initial);
      setRecursionVal(agent.data.recursion || 3);
    }
  }, [agent, allNodes, isLoop]);

  useEffect(() => {
    if (agent?.id) {
      setIsCollapsed(false);
    }
  }, [agent?.id]);

  const handlePayloadSelect = async (type: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/picker?type=${type}`);
      const data = await res.json();
      if (data.path) {
        setPayload(data.path);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (onUpdateNode && agent?.id) {
      let finalLabel = selectedAgentName;
      if (nodeType === 'WAIT/RETRY') finalLabel = 'WAIT/RETRY';
      if (nodeType === 'HUMAN_GATE') finalLabel = 'HUMAN_GATE';
      
      onUpdateNode(agent.id, {
        label: finalLabel,
        nodeType: nodeType,
        instruction,
        model,
        tools,
        project: "GLOBAL",
        payload
      });
    }
  }, [selectedAgentName, instruction, model, tools, payload, agent?.id, onUpdateNode, nodeType]);

  if (!agent) return null;

  const handleApplyRecursion = () => {
    if (onUpdateNode && onUpdateMultipleNodes) {
      onUpdateNode(agent.id, { recursion: recursionVal });
      const updates = Object.entries(liveStatuses).map(([id, isLive]) => ({ id, data: { isLive } }));
      onUpdateMultipleNodes(updates);
    }
  };

  return (
    <>
      <AnimatePresence>
        {!isCollapsed && (
          <motion.div 
            className="miniboard-slate full-height-panel"
            initial={{ x: 400, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 400, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            style={{ borderLeft: '1px solid var(--panel-border)', borderRight: 'none', fontSize: '0.8rem' }}
          >
            <div className="miniboard-header" style={{ padding: '8px 12px' }}>
              <button className="icon-btn" onClick={() => setIsCollapsed(true)} style={{ padding: '4px' }}><ChevronRight size={16} /></button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div className={`status-dot ${agent.data.isLive ? 'live' : ''}`} style={{ width: '10px', height: '10px' }} />
                <h3 style={{ fontSize: '0.9rem', margin: 0 }}>{isLoop ? 'Recursion Node' : selectedAgentName}</h3>
              </div>
              <button className="icon-btn" onClick={onClose} style={{ padding: '4px' }}><X size={16} /></button>
            </div>

            <div className="miniboard-content" style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div className="slate-section" style={{ padding: '8px' }}>
                <label style={{ fontSize: '0.75rem', marginBottom: '2px' }}>Node Type</label>
                <select 
                  className="agent-dropdown" 
                  value={nodeType}
                  onChange={(e) => setNodeType(e.target.value)}
                  style={{ width: '100%', padding: '4px', fontSize: '0.8rem' }}
                >
                  <option value="AGENT">Standard Agent</option>
                  <option value="WAIT/RETRY">Wait / Retry</option>
                  <option value="HUMAN_GATE">Human Gate</option>
                </select>
              </div>

              {nodeType === 'AGENT' && (
                <>
                  <div className="slate-section" style={{ padding: '8px' }}>
                    <label style={{ fontSize: '0.75rem', marginBottom: '2px' }}>Global Agent Pool</label>
                    <select 
                      className="agent-dropdown" 
                      value={selectedAgentName}
                      onChange={handleAgentSelect}
                      style={{ width: '100%', padding: '4px', fontSize: '0.8rem' }}
                    >
                      <option value="Unassigned Agent">-- Select Agent --</option>
                      {globalAgents.map((ag: any, idx: number) => (
                        <option key={idx} value={ag.Agent_Name}>
                          {ag.Agent_Name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="slate-section" style={{ padding: '8px' }}>
                    <label style={{ fontSize: '0.75rem', marginBottom: '2px' }}>Payload Context</label>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      <input type="text" readOnly value={payload || "No payload."} style={{ flex: 1, padding: '4px', fontSize: '0.8rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--panel-border)', color: payload ? 'white' : '#888', borderRadius: '4px' }} />
                      <button className="btn-secondary" onClick={() => handlePayloadSelect('folder')} style={{ flex: 'none', padding: '4px' }} title="Dir">
                        <FolderSearch size={14} />
                      </button>
                      <button className="btn-secondary" onClick={() => handlePayloadSelect('file')} style={{ flex: 'none', padding: '4px' }} title="File">
                        <FileSearch size={14} />
                      </button>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn-secondary" onClick={() => { setShowStudio(!showStudio); setShowAuth(false); }} style={{ flex: 1, padding: '6px', fontSize: '0.8rem' }}>
                      <Settings2 size={14} style={{ marginRight: '4px' }} /> Agent Studio
                    </button>
                    <button className="btn-secondary" onClick={() => { setShowAuth(!showAuth); setShowStudio(false); }} style={{ flex: 1, padding: '6px', fontSize: '0.8rem', color: '#ffb86c', borderColor: '#ffb86c' }}>
                      <Settings2 size={14} style={{ marginRight: '4px' }} /> Vault Auth
                    </button>
                  </div>
                </>
              )}

              {nodeType === 'WAIT/RETRY' && (
                <div className="slate-section" style={{ padding: '8px' }}>
                  <label style={{ fontSize: '0.75rem', marginBottom: '4px', borderBottom: '1px solid #333', paddingBottom: '2px', display: 'block' }}>Loop Controller Configuration</label>
                  <p style={{ margin: '4px 0 8px 0', fontSize: '0.75rem', color: '#aaa' }}>
                    Configure how many times the wait loop will tick before routing to FAILED.
                  </p>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                    <label style={{ fontSize: '0.8rem', color: '#ccc' }}>Max Loop Expiries:</label>
                    <input 
                      type="number" 
                      value={recursionVal} 
                      onChange={e => setRecursionVal(parseInt(e.target.value) || 1)}
                      style={{ width: '80px', padding: '4px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--panel-border)', color: 'white', borderRadius: '4px', fontSize: '0.8rem' }}
                      min="1"
                      max="100"
                    />
                  </div>

                  <label style={{ fontSize: '0.75rem', marginBottom: '4px', borderBottom: '1px solid #333', paddingBottom: '2px', display: 'block' }}>Live Wait Targeting</label>
                  <p style={{ margin: '4px 0 8px 0', fontSize: '0.75rem', color: '#aaa' }}>
                    Select which downstream agent this loop is actively waiting on. The Wait node will query the telemetry SQLite db until this agent reports DONE.
                  </p>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                    {Object.entries(liveStatuses).map(([id, isLive]) => {
                      const nodeObj = allNodes.find((n: any) => n.id === id);
                      const name = nodeObj?.data?.label || id;
                      if (name === 'START_NODE' || name === 'WAIT/RETRY' || name === 'HUMAN_GATE') return null;
                      return (
                        <div key={id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(255,255,255,0.02)', padding: '6px', borderRadius: '4px', border: '1px solid var(--panel-border)' }}>
                          <span style={{ fontSize: '0.8rem', color: isLive ? '#50fa7b' : '#ccc' }}>{name}</span>
                          <button 
                            className={`btn-secondary ${isLive ? 'active-toggle' : ''}`}
                            style={{ padding: '2px 8px', fontSize: '0.7rem', background: isLive ? 'rgba(80, 250, 123, 0.2)' : 'transparent', borderColor: isLive ? '#50fa7b' : 'var(--panel-border)', color: isLive ? '#50fa7b' : '#888' }}
                            onClick={() => setLiveStatuses(prev => ({ ...prev, [id]: !prev[id] }))}
                          >
                            {isLive ? 'Targeted' : 'Ignore'}
                          </button>
                        </div>
                      );
                    })}
                  </div>

                  <button className="btn-primary" onClick={handleApplyRecursion} style={{ width: '100%', marginTop: '16px', padding: '6px', fontSize: '0.8rem' }}>
                    Apply Loop Logic
                  </button>
                </div>
              )}

              {nodeType === 'HUMAN_GATE' && (
                <div className="slate-section" style={{ padding: '8px' }}>
                  <label style={{ fontSize: '0.75rem', marginBottom: '4px', borderBottom: '1px solid #333', paddingBottom: '2px', display: 'block' }}>Human Checkpoint</label>
                  <p style={{ margin: '4px 0 8px 0', fontSize: '0.75rem', color: '#aaa' }}>
                    The swarm will automatically pause when it reaches this node. 
                    You must manually inspect the generated artifacts and click "Resume Swarm" via the VCR controls to allow execution to continue downstream.
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AgentStudioSettings 
        isOpen={showStudio} 
        onClose={() => setShowStudio(false)}
        agentName={selectedAgentName}
        instruction={instruction} setInstruction={setInstruction}
        model={model} setModel={setModel}
        tools={tools} setTools={setTools}
        description={description} setDescription={setDescription}
      />
      
      <AuthPanel 
        isOpen={showAuth} 
        onClose={() => setShowAuth(false)} 
      />

      {isCollapsed && (
        <button 
          className="collapsed-toggle-btn"
          onClick={() => setIsCollapsed(false)}
          style={{ position: 'absolute', top: '80px', right: '24px', zIndex: 300, padding: '8px' }}
        >
          <ChevronLeft size={20} />
        </button>
      )}
    </>
  );
}
