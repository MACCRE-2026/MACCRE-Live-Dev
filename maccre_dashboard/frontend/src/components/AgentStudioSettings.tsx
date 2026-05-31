import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function AgentStudioSettings({ 
  isOpen, onClose, 
  agentName, 
  instruction, setInstruction,
  model, setModel,
  tools, setTools,
  description, setDescription
}: any) {
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [mintName, setMintName] = useState(agentName === "Unassigned Agent" ? "" : agentName);
  const [saveStatus, setSaveStatus] = useState("");

  // AI Studio specific settings
  const [thinkingLevel, setThinkingLevel] = useState("High");
  const [temperature, setTemperature] = useState(1.0);
  
  // Tools toggles
  const [toolCodeExec, setToolCodeExec] = useState(false);
  const [toolFunctionCall, setToolFunctionCall] = useState(false);
  const [toolGoogleSearch, setToolGoogleSearch] = useState(false);
  const [toolGoogleMaps, setToolGoogleMaps] = useState(false);
  const [toolUrlContext, setToolUrlContext] = useState(false);

  // Advanced settings
  const [mediaResolution, setMediaResolution] = useState("Default");
  const [outputLength, setOutputLength] = useState(65536);
  const [topP, setTopP] = useState(0.95);
  const [safetySettings, setSafetySettings] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetch('http://127.0.0.1:8000/api/models')
        .then(res => res.json())
        .then(data => setAvailableModels(data))
        .catch(console.error);
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && agentName !== "Unassigned Agent") {
      setMintName(agentName);
    }
  }, [agentName, isOpen]);

  const handleSave = async () => {
    if (!mintName) {
      setSaveStatus("Error: Agent Name is required to mint.");
      return;
    }
    setSaveStatus("Saving...");
    
    // Construct tools string for backend
    let enabledTools: string[] = [];
    if (toolCodeExec) enabledTools.push("code_execution");
    if (toolFunctionCall) enabledTools.push("function_calling");
    if (toolGoogleSearch) enabledTools.push("google_search");
    if (toolGoogleMaps) enabledTools.push("google_maps");
    if (toolUrlContext) enabledTools.push("url_context");
    // Also include custom tools typed into the tools string input (if any)
    const customTools = tools ? tools.split("|").map((t: string) => t.trim()).filter((t: string) => t) : [];
    const finalTools = [...new Set([...enabledTools, ...customTools])].join("|") || "none";

    try {
      const res = await fetch('http://127.0.0.1:8000/api/agents/mint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_name: mintName,
          model: model || availableModels[0] || "gemini-3.1-pro-preview",
          tools: finalTools,
          system_prompt: instruction || "You are a helpful assistant.",
          description: description || "Swarm Agent",
          thinking_level: thinkingLevel,
          temperature: temperature,
          media_resolution: mediaResolution,
          output_length: outputLength,
          top_p: topP,
          safety_settings: safetySettings
        })
      });
      const data = await res.json();
      if (data.status === "success") {
        setSaveStatus(`Saved Globally!`);
      } else {
        setSaveStatus(`Error: ${data.detail || data.message}`);
      }
    } catch (e: any) {
      setSaveStatus(`Error: ${e.message}`);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div 
          className="miniboard-slate ancillary-popout"
          initial={{ x: 300, opacity: 0 }}
          animate={{ x: -416, opacity: 1 }}
          exit={{ x: 300, opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          style={{ position: 'absolute', zIndex: 199, height: 'calc(100vh - 100px)', top: '50px', width: '600px', fontSize: '0.8rem' }}
        >
          <div className="miniboard-header" style={{ background: 'rgba(0, 204, 255, 0.1)', borderBottom: '1px solid #00ccff', padding: '8px 12px' }}>
            <h3 style={{ color: '#00ccff', margin: 0, fontSize: '0.9rem' }}>AI Studio Global Agent Settings</h3>
            <button className="icon-btn" onClick={onClose} style={{ padding: '4px' }}><X size={16} /></button>
          </div>

          <div className="miniboard-content" style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '12px' }}>
            
            <div style={{ display: 'flex', gap: '8px' }}>
              <div className="slate-section" style={{ flex: 1, padding: '8px' }}>
                <label style={{ fontSize: '0.75rem', marginBottom: '2px' }}>Model</label>
                <select className="agent-dropdown" value={model} onChange={e => setModel(e.target.value)} style={{ width: '100%', padding: '4px', fontSize: '0.8rem' }}>
                  {availableModels.length === 0 ? <option value="">-- Loading Models... --</option> : <option value="">-- Select Model --</option>}
                  {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div className="slate-section" style={{ flex: 1, padding: '8px' }}>
                <label style={{ fontSize: '0.75rem', marginBottom: '2px' }}>Agent Name (Global ID)</label>
                <input type="text" value={mintName} onChange={e => setMintName(e.target.value)} placeholder="e.g., TIGR_Architect" style={{ width: '100%', padding: '4px', fontSize: '0.8rem', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--panel-border)', color: 'white', borderRadius: '4px' }} />
              </div>
            </div>

            <div className="slate-section" style={{ flex: 1, padding: '8px', display: 'flex', flexDirection: 'column' }}>
              <label style={{ fontSize: '0.75rem', marginBottom: '2px' }}>System Instructions</label>
              <textarea 
                className="nudge-editor"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                style={{ flex: 1, fontSize: '0.8rem', padding: '6px' }}
              />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <div className="slate-section" style={{ flex: 1, padding: '8px' }}>
                <label style={{ fontSize: '0.75rem', marginBottom: '2px' }}>Temperature: {temperature}</label>
                <input type="range" min="0" max="2" step="0.1" value={temperature} onChange={(e) => setTemperature(parseFloat(e.target.value))} style={{ width: '100%' }} />
                
                <label style={{ fontSize: '0.75rem', marginTop: '8px', marginBottom: '2px' }}>Thinking Level</label>
                <select value={thinkingLevel} onChange={(e) => setThinkingLevel(e.target.value)} style={{ width: '100%', padding: '4px', fontSize: '0.8rem', background: 'rgba(0,0,0,0.3)', color: 'white', border: '1px solid var(--panel-border)' }}>
                  <option value="High">High</option>
                  <option value="Default">Default</option>
                  <option value="Low">Low</option>
                </select>
              </div>

              <div className="slate-section" style={{ flex: 1, padding: '8px' }}>
                <label style={{ fontSize: '0.75rem', marginBottom: '4px', borderBottom: '1px solid #333', paddingBottom: '2px' }}>Tools</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input type="checkbox" checked={toolCodeExec} onChange={(e) => setToolCodeExec(e.target.checked)} /> Code execution
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input type="checkbox" checked={toolFunctionCall} onChange={(e) => setToolFunctionCall(e.target.checked)} /> Function calling
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input type="checkbox" checked={toolGoogleSearch} onChange={(e) => setToolGoogleSearch(e.target.checked)} /> Grounding with Google Search
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input type="checkbox" checked={toolGoogleMaps} onChange={(e) => setToolGoogleMaps(e.target.checked)} /> Grounding with Google Maps
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input type="checkbox" checked={toolUrlContext} onChange={(e) => setToolUrlContext(e.target.checked)} /> URL context
                  </label>
                </div>
              </div>
            </div>

            <div className="slate-section" style={{ padding: '8px' }}>
              <label style={{ fontSize: '0.75rem', marginBottom: '4px', borderBottom: '1px solid #333', paddingBottom: '2px', display: 'block' }}>Advanced Settings</label>
              <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.7rem' }}>Media resolution</label>
                  <select value={mediaResolution} onChange={(e) => setMediaResolution(e.target.value)} style={{ width: '100%', padding: '4px', fontSize: '0.8rem', background: 'rgba(0,0,0,0.3)', color: 'white', border: '1px solid var(--panel-border)' }}>
                    <option value="Default">Default</option>
                    <option value="High">High</option>
                    <option value="Low">Low</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.7rem' }}>Output length</label>
                  <input type="number" value={outputLength} onChange={(e) => setOutputLength(parseInt(e.target.value))} style={{ width: '100%', padding: '4px', fontSize: '0.8rem', background: 'rgba(0,0,0,0.3)', color: 'white', border: '1px solid var(--panel-border)' }} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.7rem' }}>Top P: {topP}</label>
                  <input type="range" min="0" max="1" step="0.05" value={topP} onChange={(e) => setTopP(parseFloat(e.target.value))} style={{ width: '100%' }} />
                </div>
              </div>
              <div style={{ marginTop: '12px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: '#ffb86c' }}>
                  <input type="checkbox" checked={safetySettings} onChange={(e) => setSafetySettings(e.target.checked)} />
                  Enable Safety Settings (Filters)
                </label>
              </div>
            </div>

            <div className="slate-section" style={{ padding: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: saveStatus.includes('Error') ? '#ff5555' : '#50fa7b', fontSize: '0.75rem' }}>{saveStatus}</span>
              <button className="btn-primary" onClick={handleSave} style={{ width: 'auto', padding: '6px 12px', fontSize: '0.8rem' }}>Save Global Profile</button>
            </div>

          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
