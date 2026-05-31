import { useState, useEffect } from 'react';
import { PlusCircle, Box, Activity, ChevronLeft, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function LeftPanel() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeProject, setActiveProject] = useState("GLOBAL");
  const [projects, setProjects] = useState<string[]>([]);

  const fetchProjects = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/projects');
      const data = await res.json();
      setActiveProject(data.active);
      setProjects(data.projects);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleSwitchProject = async (e: any) => {
    const proj = e.target.value;
    try {
      await fetch('http://127.0.0.1:8000/api/projects/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: proj })
      });
      fetchProjects();
    } catch (e) { console.error(e); }
  };

  const handleNewProject = async () => {
    const proj = window.prompt("Enter new Datacenter Project name (alphanumeric_only):");
    if (proj) {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/projects/new', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_name: proj })
        });
        const data = await res.json();
        if (data.status === 'success') {
          fetchProjects();
        } else {
          alert("Error: " + data.detail);
        }
      } catch (e) { console.error(e); }
    }
  };

  const onDragStart = (event: React.DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <>
      <AnimatePresence>
        {!isCollapsed && (
          <motion.div 
            className="left-panel-roster full-height-panel"
            initial={{ x: -400, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -400, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
          >
            <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0 }}>MACCRE TAR</h3>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Topology and Agent Roster</span>
              </div>
              <button className="icon-btn" onClick={() => setIsCollapsed(true)}><ChevronLeft size={20} /></button>
            </div>
            
            <div className="panel-content" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              <div className="slate-section" style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Active Project (Silo)</label>
                <select 
                  className="agent-dropdown" 
                  value={activeProject || "GLOBAL"} 
                  onChange={handleSwitchProject}
                  style={{ width: '100%', padding: '6px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--panel-border)', color: 'white', borderRadius: '4px', marginTop: '4px' }}
                >
                  <option value="GLOBAL">GLOBAL (All Silos)</option>
                  {(projects || []).filter(p => p !== 'GLOBAL').map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>

              <p className="panel-desc">Drag blobs to spawn nodes on the topology.</p>
              
              <div 
                className="draggable-blob" 
                onDragStart={(event) => onDragStart(event, 'agentNode')} 
                draggable
              >
                <Box size={18} />
                <span>Standard Node Blob</span>
              </div>

              <div 
                className="draggable-blob loop-blob" 
                onDragStart={(event) => onDragStart(event, 'loopNode')} 
                draggable
              >
                <Activity size={18} />
                <span>Wait / Retry Loop</span>
              </div>

              <button className="btn-secondary add-project-btn" style={{ marginTop: 'auto' }} onClick={handleNewProject}>
                <PlusCircle size={16} /> New Datacenter Project
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {isCollapsed && (
        <button 
          className="collapsed-toggle-btn"
          onClick={() => setIsCollapsed(false)}
          style={{ position: 'absolute', top: '24px', left: '24px', zIndex: 300 }}
        >
          <ChevronRight size={24} />
        </button>
      )}
    </>
  );
}
